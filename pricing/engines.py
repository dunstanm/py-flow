"""
pricing/engines — Execution strategies for portfolios and instruments.

Decouples the 'how' (execution engine) from the 'what' (instrument portfolio).
Provides Python, SQL (CTE-optimized), and Skinny Table (basis-extracted) engines.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple
from collections import Counter

from reactive.expr import (
    Expr, Const, Variable, VariableMixin, Field, BinOp, UnaryOp, Func, If, Sum,
    eval_cached, diff
)
from reactive.basis_extractor import BasisExtractor

class ExecutionEngine:
    """Base class for all pricing execution strategies."""
    def evaluate(self, portfolio: Any, ctx: dict) -> dict:
        raise NotImplementedError()

class PythonEngine(ExecutionEngine):
    """Native Python execution using symbolic expression evaluation."""
    def npvs(self, portfolio: Any, ctx: dict) -> dict[str, float]:
        """Evaluate all NPVs."""
        return {name: eval_cached(expr, ctx) for name, expr in portfolio.npv_exprs.items()}

    def residuals(self, portfolio: Any, ctx: dict) -> dict[str, float]:
        """Evaluate residual vector (what the fitter minimizes)."""
        return {name: eval_cached(expr, ctx) for name, expr in portfolio.residual_exprs.items()}

    def instrument_risk(self, portfolio: Any, ctx: dict) -> dict[str, dict[str, float]]:
        """Evaluate the risk per instrument (full Jacobian matrix)."""
        cache: dict = {}
        return {
            name: {label: eval_cached(expr, ctx, _cache=cache) for label, expr in row.items()}
            for name, row in portfolio.jacobian_exprs.items()
        }

    def total_risk(self, portfolio: Any, ctx: dict) -> dict[str, float]:
        """Aggregate ∂(Σnpv)/∂pillar across all pricing.instruments."""
        total_expr = portfolio.total_npv_expr
        cache: dict = {}
        return {
            pillar_name: eval_cached(diff(total_expr, pillar_name), ctx, _cache=cache)
            for pillar_name in portfolio.pillar_names
        }

class SQLEngine(ExecutionEngine):
    """Generates optimized CTE-based SQL for executing the entire portfolio.
    
    Preserves sub-expression sharing by mapping the Expr DAG to a 
    topologically sorted chain of Common Table Expressions.
    """
    def generate_sql(self, portfolio: Any, ctx: dict[str, float]) -> str:
        # 1. Identify all target expressions
        npv_targets = portfolio.npv_exprs
        jac_targets = portfolio.jacobian_exprs
        
        all_exprs: list[Expr] = list(npv_targets.values())
        relevant_jac: dict[str, dict[str, Expr]] = {}

        for swap_name, row in jac_targets.items():
            relevant_jac[swap_name] = {}
            for pillar, expr in row.items():
                if isinstance(expr, Const) and expr.value == 0.0:
                    continue 
                relevant_jac[swap_name][pillar] = expr
                all_exprs.append(expr)

        # 2. Find shared nodes (in-degree > 1 across the whole portfolio)
        node_counts: Counter[int] = Counter()
        def _collect(e: Expr, visited: set[int]):
            node_counts[id(e)] += 1
            if id(e) in visited: return
            visited.add(id(e))
            for child in _get_children(e):
                _collect(child, visited)

        global_visited: set[int] = set()
        for expr in all_exprs:
            _collect(expr, global_visited)

        shared_node_ids = {nid for nid, count in node_counts.items() if count > 1}

        # 3. Topological sort of shared nodes
        ordered_shared: list[Expr] = []
        visited_shared = set()
        def _topo(e: Expr):
            if id(e) in visited_shared: return
            for child in _get_children(e):
                _topo(child)
            if id(e) in shared_node_ids:
                visited_shared.add(id(e))
                ordered_shared.append(e)

        for expr in all_exprs:
            _topo(expr)

        # 4. Generate SQL fragments
        cte_defs = []
        pillar_cols = ", ".join(f'{rate} AS "{name}"' for name, rate in ctx.items())
        cte_defs.append(f'pillars AS (SELECT {pillar_cols})')

        subst: dict[int, str] = {}
        def _get_sql(e: Expr) -> str:
            return _to_sql_dag(e, subst, "pillars")

        for i, node in enumerate(ordered_shared):
            if isinstance(node, (Variable, VariableMixin, Const)):
                subst[id(node)] = _get_sql(node)
                continue

            name = f"node_{i}"
            sql = _get_sql(node)
            from_clause = "pillars" # Simplified dependency chain for now
            cte_defs.append(f'{name} AS (SELECT ({sql}) AS val FROM {from_clause})')
            subst[id(node)] = f"{name}.val"

        select_cols = []
        for name, expr in npv_targets.items():
            select_cols.append(f'{_get_sql(expr)} AS "{name}_NPV"')
        
        for swap_name, row in relevant_jac.items():
            for pillar, expr in row.items():
                select_cols.append(f'{_get_sql(expr)} AS "{swap_name}_dNPV_d{pillar}"')

        return "WITH " + ",\n  ".join(cte_defs) + "\nSELECT\n  " + ",\n  ".join(select_cols) + "\nFROM pillars"

class SkinnyEngine(ExecutionEngine):
    """Execution via 'Skinny Table' basis function extraction.
    
    Splits expressions into (BasisFunction, Weights) for vectorized 
    evaluation in DuckDB, NumPy, or Deephaven.
    """
    def __init__(self, extractor: BasisExtractor | None = None):
        self.extractor = extractor or BasisExtractor()

    def to_components(self, portfolio: Any, per_swap=True) -> list[dict]:
        agg_map: dict[tuple, float] = {}

        def _add_to_agg(trade_name, comp_class, expr):
            trade_components = self.extractor.extract_components(expr)
            for bf, vars, params, weight in trade_components:
                key_prefix = (trade_name if per_swap else None, comp_class, bf.component_type)
                full_key = key_prefix + tuple(vars) + tuple(params)
                agg_map[full_key] = agg_map.get(full_key, 0.0) + weight

        for name, expr in portfolio.npv_exprs.items():
            _add_to_agg(name, "NPV", expr)
        for name, row_exprs in portfolio.jacobian_exprs.items():
            for pillar, expr in row_exprs.items():
                if not (isinstance(expr, Const) and expr.value == 0.0):
                    _add_to_agg(name, f"dNPV_d{pillar}", expr)

        res = []
        for key, total_weight in agg_map.items():
            trade_name, comp_class, comp_type = key[:3]
            bf = self.extractor.registry_by_type[comp_type]
            row = {"Component_Class": comp_class, "Component_Type": comp_type, "Weight": total_weight}
            if per_swap: row["Swap_Id"] = trade_name
            for j, v in enumerate(key[3:3 + bf.num_vars]): row[f"X{j+1}"] = v
            for j, p in enumerate(key[3 + bf.num_vars:]): row[f"p{j+1}"] = p
            res.append(row)
        return res

    def generate_duckdb_sql(self, portfolio: Any, per_swap=True) -> str:
        max_vars = max((bf.num_vars for bf in self.extractor.registry.values()), default=1)
        select_cols = []
        if per_swap: select_cols.append("c.Swap_Id")
        
        math_case_lines = []
        for bf in self.extractor.registry.values():
            s_expr = bf.sql_template.replace("^", "**")
            for j in range(1, bf.num_vars + 1):
                s_expr = s_expr.replace(f"X{j}", f"s{j}.Knot_Value")
            math_case_lines.append(f"                WHEN {bf.component_type} THEN {s_expr}")
        
        math_case = "CASE c.Component_Type\n" + "\n".join(math_case_lines) + "\n            END"
        select_cols.append(f"SUM(CASE WHEN c.Component_Class = 'NPV' THEN c.Weight * ({math_case}) ELSE 0.0 END) as NPV")
        
        for pillar in portfolio.pillar_names:
            select_cols.append(f"SUM(CASE WHEN c.Component_Class = 'dNPV_{pillar}' THEN c.Weight * ({math_case}) ELSE 0.0 END) as \"{pillar}\"")
        
        group_by = "sc.Scenario_Id" + (", c.Swap_Id" if per_swap else "")
        joins = ["FROM t_components c", "    CROSS JOIN (SELECT DISTINCT Scenario_Id FROM t_scenarios) sc"]
        for j in range(1, max_vars + 1):
            joins.append(f"    LEFT JOIN t_scenarios s{j} ON c.X{j} = s{j}.Knot_Id AND sc.Scenario_Id = s{j}.Scenario_Id")
            
        return f"SELECT\n    {group_by},\n    {', '.join(select_cols)}\n{' '.join(joins)}\nGROUP BY {group_by}"


# ── Internal Helpers ───────────────────────────────────────────────────────

def _get_children(expr: Expr) -> list[Expr]:
    if isinstance(expr, Sum): return list(expr.terms)
    if isinstance(expr, BinOp): return [expr.left, expr.right]
    if isinstance(expr, UnaryOp): return [expr.operand]
    if isinstance(expr, Func): return list(expr.args)
    if isinstance(expr, If): return [expr.condition, expr.then_, expr.else_]
    return []

def _to_sql_dag(expr: Expr, subst: dict[int, str], col: str) -> str:
    if id(expr) in subst: return subst[id(expr)]
    if isinstance(expr, (Variable, VariableMixin)): return expr.expr_to_sql(col)
    if isinstance(expr, Const): return expr.to_sql(col)
    if isinstance(expr, Sum):
        parts = [_to_sql_dag(t, subst, col) for t in expr.terms]
        return "(" + " + ".join(parts) + ")" if parts else "0"
    if isinstance(expr, BinOp):
        from reactive.expr import _SQL_OPS
        return f"({_to_sql_dag(expr.left, subst, col)} {_SQL_OPS[expr.op]} {_to_sql_dag(expr.right, subst, col)})"
    return expr.to_sql(col)
