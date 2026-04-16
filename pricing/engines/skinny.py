from __future__ import annotations
from typing import Any
import pandas as pd
import numpy as np
from reactive.expr import Const
from reactive.basis_extractor import BasisExtractor
from pricing.engines.base import ExecutionEngine

class SkinnyEngineBase(ExecutionEngine):
    """Base engine for 'Skinny Table' component extraction.
    
    Splits portfolio expressions into (BasisFunction, Weights) components.
    Subclasses provide specific execution/projection for these components.
    """
    def __init__(self, extractor: BasisExtractor | None = None):
        self.extractor = extractor or BasisExtractor()

    def to_components(self, portfolio: Any, per_swap=True, risk_method: Any = None, **kwargs) -> list[dict]:
        """Extract the flat table of components."""
        agg_map: dict[tuple, float] = {}

        def _add_to_agg(trade_name, comp_class, expr):
            trade_components = self.extractor.extract_components(expr)
            for bf, vars, params, weight in trade_components:
                key_prefix = (trade_name if per_swap else None, comp_class, bf.component_type)
                full_key = key_prefix + tuple(vars) + tuple(params)
                agg_map[full_key] = agg_map.get(full_key, 0.0) + weight

        from pricing.risk.firstorder_analytic import FirstOrderAnalyticRisk
        from pricing.risk.firstorder_numeric import FirstOrderNumericalRisk
        
        # If numerical risk is requested here, it means we want the result of bumping 
        # but expressed in terms of components. This is only possible if we re-extract 
        # or if the risk helper returns Exprs. Numerical risk helper returns floats,
        # so we'd have to wrap them as Const Exprs if we wanted to stick to the component path.
        if risk_method and issubclass(risk_method, FirstOrderNumericalRisk):
            # For simplicity, we'll extract NPV components and then also 
            # add components for the numerical sensitivities as 'Const' weights.
            # (Warning: inefficient, better to just use Analytic for skinny)
            calc = risk_method(portfolio)
            risk_results = calc.instrument_risk(**kwargs)
            
            # 1. Add normal NPV components
            for name, expr in portfolio.npv_exprs.items():
                _add_to_agg(name, "NPV", expr)
            
            # 2. Add Numerical risk as static component weights
            for name, row in risk_results.items():
                for pillar, val in row.items():
                    _add_to_agg(name, f"dNPV_d{pillar}", Const(val))
        else:
            method = risk_method or FirstOrderAnalyticRisk
            calc = method(portfolio)
            risk_map = calc.instrument_risk(**kwargs)

            for name, expr in portfolio.npv_exprs.items():
                _add_to_agg(name, "NPV", expr)
            for name, row_exprs in risk_map.items():
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

class SkinnyEngineDuckDB(SkinnyEngineBase):
    """Project components into DuckDB SQL."""
    def generate_sql(self, portfolio: Any, per_swap=True, risk_method: Any = None, **kwargs) -> str:
        comps = self.to_components(portfolio, per_swap=per_swap, risk_method=risk_method, **kwargs)
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
            select_cols.append(f"SUM(CASE WHEN c.Component_Class = 'dNPV_d{pillar}' THEN c.Weight * ({math_case}) ELSE 0.0 END) as \"{pillar}\"")
        
        group_by = "sc.Scenario_Id" + (", c.Swap_Id" if per_swap else "")
        joins = ["FROM t_components c", "    CROSS JOIN (SELECT DISTINCT Scenario_Id FROM t_scenarios) sc"]
        for j in range(1, max_vars + 1):
            joins.append(f"    LEFT JOIN t_scenarios s{j} ON c.X{j} = s{j}.Knot_Id AND sc.Scenario_Id = s{j}.Scenario_Id")
            
        return f"SELECT\n    {group_by},\n    {', '.join(select_cols)}\n{' '.join(joins)}\nGROUP BY {group_by}"

class SkinnyEngineNumPy(SkinnyEngineBase):
    """Execute components via NumPy vectorized arrays."""
    def evaluate(self, portfolio: Any, ctx: dict, risk_method: Any = None, **kwargs) -> pd.DataFrame:
        comps = self.to_components(portfolio, per_swap=True, risk_method=risk_method, **kwargs)
        df = pd.DataFrame(comps)
        
        type_map = {bf.component_type: bf for bf in self.extractor.registry.values()}
        for bf in type_map.values():
            if not hasattr(bf, "_compiled_np"):
                py_code = bf.dh_template.replace("Math.pow", "np.power").replace("Math.exp", "np.exp")
                bf._compiled_np = compile(py_code, f"<basis_{bf.component_type}>", "eval")
        
        groups = df.groupby(["Swap_Id", "Component_Class", "Component_Type"])
        results = []
        for (sid, c_class, c_type), group in groups:
            bf = type_map[c_type]
            params = {f"p{j}": group[f"p{j}"].values for j in range(1, bf.num_params + 1)}
            vars = {f"X{j}": np.array([ctx.get(k, 0.04) for k in group[f"X{j}"]]) for j in range(1, bf.num_vars + 1)}
            ns = {"np": np, **params, **vars}
            val = np.sum(eval(bf._compiled_np, {"np": np}, ns) * group["Weight"].values)
            results.append({"Swap_Id": sid, "Metric": c_class, "Value": val})
            
        res_df = pd.DataFrame(results)
        res_df = res_df.groupby(["Swap_Id", "Metric"])["Value"].sum().reset_index()
        return res_df.pivot(index="Swap_Id", columns="Metric", values="Value")

class SkinnyEngineDeephaven(SkinnyEngineBase):
    """Project components into Deephaven streaming scripts."""
    def generate_script(self, portfolio: Any, per_swap=True) -> str:
        dh_lines = []
        for bf in self.extractor.registry.values():
            tmpl = bf.dh_template.replace("Math.pow", "pow").replace("Math.exp", "exp")
            for j in range(1, bf.num_vars + 1):
                tmpl = tmpl.replace(f"X{j}", f"X{j}_Val")
            dh_lines.append(f"Component_Type == {bf.component_type} ? {tmpl} :")
        full_ternary = " ".join(dh_lines) + " 0.0"

        # Note: This is a template script that assumes t_c (components) 
        # and t_p (pillars) are already defined in the Deephaven session.
        script = f"""
t_mapped = t_c.natural_join(t_p, on=['X1=Knot_Id'], joins=['X1_Val=Knot_Value'])
t_mapped = t_mapped.natural_join(t_p, on=['X2=Knot_Id'], joins=['X2_Val=Knot_Value'])
t_mapped = t_mapped.update(["X1_Val = (X1_Val == null) ? 0.04 : X1_Val", "X2_Val = (X2_Val == null) ? 0.04 : X2_Val"])

t_evaluated = t_mapped.update(["Out = (double)(Weight * ({full_ternary}))"])
t_filtered = t_evaluated.view(["Swap_Id", "Component_Class", "Out"])

t_npv_res = t_filtered.where(["Component_Class == `NPV`"]).agg_by([agg.sum_("Out")], ["Swap_Id"])
t_risk_swap_res = t_filtered.agg_by([agg.sum_("Out")], ["Swap_Id", "Component_Class"])
t_risk_total_res = t_filtered.agg_by([agg.sum_("Out")], ["Component_Class"])
"""
        return script
