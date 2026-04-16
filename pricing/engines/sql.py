from __future__ import annotations
from typing import Any
from collections import Counter
from reactive.expr import (
    Expr, Const, Variable, VariableMixin, BinOp, UnaryOp, Func, If, Sum
)
from pricing.engines.base import ExecutionEngine

class SQLEngineCTE(ExecutionEngine):
    """Generates optimized CTE-based SQL for executing the entire portfolio.
    
    This engine maps the full expression DAG to a chain of Common Table Expressions.
    Ideal for batch SQL (DuckDB, Snowflake) where sub-expression sharing matters.
    """
    def generate_sql(self, portfolio: Any, ctx: dict[str, float], risk_method: Any = None, **kwargs) -> str:
        # 1. Identify all target expressions
        from pricing.risk.firstorder_analytic import FirstOrderAnalyticRisk
        from pricing.risk.firstorder_numeric import FirstOrderNumericalRisk
        
        method = risk_method or FirstOrderAnalyticRisk
        calc = method(portfolio)

        npv_targets = portfolio.npv_exprs
        risk_targets = calc.instrument_risk(**kwargs)
        
        all_exprs: list[Expr] = list(npv_targets.values())
        relevant_risk: dict[str, dict[str, Expr]] = {}

        for swap_name, row in risk_targets.items():
            relevant_risk[swap_name] = {}
            for pillar, val in row.items():
                # If numerical, wrap the float results as Const Exprs
                expr = val if not isinstance(val, (float, int)) else Const(val)
                relevant_risk[swap_name][pillar] = expr
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
        
        for swap_name, row in relevant_risk.items():
            for pillar, expr in row.items():
                select_cols.append(f'{_get_sql(expr)} AS "{swap_name}_dNPV_d{pillar}"')

        return "WITH " + ",\n  ".join(cte_defs) + "\nSELECT\n  " + ",\n  ".join(select_cols) + "\nFROM pillars"


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
