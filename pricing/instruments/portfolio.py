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
from pricing.instruments.base import Instrument


class Portfolio(Instrument):
    """A collection of named swap Expr trees on a shared curve.
    ...
    """

    def __init__(self):
        # Instrument.__init__ is not called because we have no dataclass fields
        # but we need to initialize reaktiv manually if we want it to work as storable
        # For now, stay as a plain object inheriting the interface.
        self._instruments: dict[str, Instrument] = {}

    def add_instrument(self, name: str, instrument: Instrument):
        """Add any pre-constructed instrument (swap, etc.) to the portfolio.
        Must support .npv() and optionally .notional.
        """
        self._instruments[name] = instrument
        return instrument

    @property
    def names(self) -> list[str]:
        return list(self._instruments.keys())

    def npv(self) -> Expr:
        """Total NPV of the portfolio as a single expression tree."""
        return sum(inst.npv() for inst in self._instruments.values())

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
        return sum(inst.npv() for inst in self._instruments.values())

    # ── Convenience evaluators ─────────────────────────────────────────

    def pillar_points(self) -> dict[str, Any]:
        """Aggregate all pillar point objects from child pricing.instruments."""
        points = {}
        for inst in self._instruments.values():
            points.update(inst.pillar_points())
        return points

    @property
    def pillar_names(self) -> list[str]:
        """Unified list of all pillar names across the portfolio."""
        names = set()
        for inst in self._instruments.values():
            names.update(inst.pillar_names)
        return sorted(list(names))

    def pillar_context(self) -> dict[str, float]:
        """Current pillar rates aggregated from all instruments' curves."""
        return {name: p.rate for name, p in self.pillar_points().items()}

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
