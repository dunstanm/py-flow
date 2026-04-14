"""
instruments/portfolio — Named collection of instrument Expr trees.

Provides the Portfolio class, which aggregates multiple IRSwapFixedFloatApprox
Expr trees on a shared curve.  This enables maximum sub-expression sharing
and provides symbolic Jacobian matrices for the fitter.
"""

from __future__ import annotations
from collections import Counter
from typing import Any

from reactive.expr import (
    Const, Expr, diff, eval_cached, 
    Variable, VariableMixin, Field,
    BinOp, UnaryOp, Func, If, Coalesce, IsNull, StrOp,
    _cast_numeric_sql
)
from pricing.instruments.ir_swap_fixed_floatapprox import IRSwapFixedFloatApprox


class Portfolio:
    """A collection of named swap Expr trees on a shared curve.

    Because all swaps call the same curve's df(t), and df
    caches Expr objects, the portfolio's expression graph has maximum
    sub-expression sharing.  For example, df(5.0) is the same
    Python object in the 5Y swap's tree and the 10Y swap's tree.

    Provides:
      .npv_exprs         → {name: Expr}           named NPV expressions
      .residual_exprs    → {name: Expr}           NPV/notional (for fitter)
      .risk_exprs        → {name: {pillar: Expr}} per-swap Jacobian rows
      .jacobian_exprs    → {name: {pillar: Expr}} ∂residual/∂pillar (for fitter)
      .total_npv_expr    → Expr                   Σ NPV across portfolio

    All return Expr trees — eval(ctx) for Python, to_sql() for SQL.
    """

    def __init__(self):
        self._instruments: dict[str, Any] = {}
        self._all_pillar_names: set[str] = set()

    def add_instrument(self, name: str, instrument: Any):
        """Add any pre-constructed instrument (swap, etc.) to the portfolio.
        Must support .npv() and optionally .notional.
        """
        self._instruments[name] = instrument
        # Update pillar names union
        if hasattr(instrument, "pillar_names"):
            self._all_pillar_names.update(instrument.pillar_names)
        return instrument

    @property
    def names(self) -> list[str]:
        return list(self._instruments.keys())

    @property
    def pillar_names(self) -> list[str]:
        return sorted(list(self._all_pillar_names))

    # ── Named dictionaries of Expr trees ───────────────────────────────

    @property
    def npv_exprs(self) -> dict[str, Expr]:
        """Named NPV expressions: {name: npv_expr}."""
        return {name: inst.npv() for name, inst in self._instruments.items()}

    @property
    def residual_exprs(self) -> dict[str, Expr]:
        """NPV / notional for each instrument (what the fitter minimizes)."""
        res = {}
        for name, inst in self._instruments.items():
            notional = getattr(inst, "notional", 
                       getattr(inst, "leg1_notional", 1.0))
            res[name] = inst.npv() * Const(1.0 / notional)
        return res

    @property
    def total_npv_expr(self) -> Expr:
        """Sum of all NPVs — a single Expr tree."""
        from reactive.expr import Sum
        return Sum([inst.npv() for inst in self._instruments.values()])

    @property
    def risk_exprs(self) -> dict[str, dict[str, Expr]]:
        """Per-instrument risk: {name: {pillar: ∂npv/∂pillar Expr}}."""
        memo: dict = {}
        pillars = self.pillar_names
        return {
            name: {
                pillar_name: diff(inst.npv(), pillar_name, _memo=memo)
                for pillar_name in pillars
            }
            for name, inst in self._instruments.items()
        }

    @property
    def jacobian_exprs(self) -> dict[str, dict[str, Expr]]:
        """Fitter Jacobian: ∂residual_i / ∂pillar_j as Expr trees.
        Each row is an instrument, each column is a pillar.
        """
        result = {}
        memo: dict = {}
        pillars = self.pillar_names
        for name, inst in self._instruments.items():
            notional = getattr(inst, "notional", 
                       getattr(inst, "leg1_notional", 1.0))
            scale = Const(1.0 / notional)
            result[name] = {
                pillar_name: diff(inst.npv(), pillar_name, _memo=memo) * scale
                for pillar_name in pillars
            }
        return result

    # ── Convenience evaluators ─────────────────────────────────────────

    def pillar_context(self) -> dict[str, float]:
        """Current pillar rates aggregated from all instruments' curves."""
        ctx = {}
        for inst in self._instruments.values():
            if hasattr(inst, "pillar_context"):
                ctx.update(inst.pillar_context())
        return ctx

    # ── Sub-expression sharing stats ───────────────────────────────────

    def shared_nodes(self) -> dict[str, int]:
        """Count how many instruments reference each cached node."""
        node_ids: Counter[int] = Counter()
        for inst in self._instruments.values():
            seen = set()
            _walk_ids(inst.npv(), seen)
            for nid in seen:
                node_ids[nid] += 1
        return {f"node_{nid}": count for nid, count in node_ids.items() if count > 1}


def _get_children(expr: Expr) -> list[Expr]:
    """Helper to extract child expressions from any node type."""
    from reactive.expr import Sum
    if isinstance(expr, Sum):
        return list(expr.terms)
    if isinstance(expr, BinOp):
        return [expr.left, expr.right]
    if isinstance(expr, UnaryOp):
        return [expr.operand]
    if isinstance(expr, (Func, Coalesce)):
        return list(getattr(expr, 'args', [])) if isinstance(expr, Func) else list(getattr(expr, 'exprs', []))
    if isinstance(expr, If):
        return [expr.condition, expr.then_, expr.else_]
    if isinstance(expr, (IsNull, StrOp)):
        res = [expr.operand]
        if hasattr(expr, 'arg') and expr.arg:
            res.append(expr.arg)
        return res
    return []


def _walk_ids(expr: Expr, seen: set[int]) -> None:
    """Walk an Expr tree collecting node ids."""
    nid = id(expr)
    if nid in seen:
        return
    seen.add(nid)
    for child in _get_children(expr):
        _walk_ids(child, seen)


def expr_to_executable_sql(expr: Expr, ctx: dict[str, float]) -> str:
    """Wrap an Expr's to_sql() fragment in a complete executable query."""
    cols = ", ".join(f'{rate} AS "{name}"' for name, rate in ctx.items())
    fragment = expr.to_sql()
    return f'WITH pillars AS (SELECT {cols})\nSELECT ({fragment}) AS result FROM pillars'
