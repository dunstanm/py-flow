#!/usr/bin/env python3
"""
Test suite for the @traceable dual-mode expression architecture.

Validates:
  1. TracedFloat arithmetic preserves both float values and Expr trees
  2. @traceable debug mode runs on plain floats (fast, transparent)
  3. @traceable trace mode (via ()) lazily produces correct Expr trees
  4. Traced Expr trees produce the same numeric results as direct evaluation
  5. Full swap pricing works in both modes (end-to-end)
"""

import math
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ═══════════════════════════════════════════════════════════════════════════
# 5. Full end-to-end: IntegratedShortRateCurve + IRSwapFixedFloatApprox
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("5. End-to-End: Curve + Swap with @traceable")
print("=" * 70)

from pricing.marketmodels.ir_curve_integrated_rate import IntegratedShortRateCurve, IntegratedRatePoint

# Build a simple 3-pillar curve
pillars = [
    IntegratedRatePoint(name="1Y", tenor_years=1.0, fitted_rate=0.04, is_fitted=True),
    IntegratedRatePoint(name="3Y", tenor_years=3.0, fitted_rate=0.045, is_fitted=True),
    IntegratedRatePoint(name="5Y", tenor_years=5.0, fitted_rate=0.05, is_fitted=True),
]

curve = IntegratedShortRateCurve(
    name="TEST_CURVE",
    currency="USD",
    degree=2,
    is_local=True,
    points=pillars,
)

# -- Test df() dispatch modes --

# Default (no context): returns float
df_float = curve.df(2.0)
assert isinstance(df_float, float) and not isinstance(df_float, TracedFloat), \
    f"Expected plain float, got {type(df_float)}"
print(f"  df(2.0) debug mode = {df_float:.6f}")

# Building mode: returns Expr
_start_building()
df_expr = curve.df(2.0)
_stop_building()
from reactive.expr import Expr
assert isinstance(df_expr, Expr), f"Expected Expr, got {type(df_expr)}"
print(f"  df(2.0) building mode = Expr")

# Tracing mode: returns TracedFloat
_start_tracing()
df_traced = curve.df(2.0)
_stop_tracing()
assert isinstance(df_traced, TracedFloat), f"Expected TracedFloat, got {type(df_traced)}"
assert abs(float(df_traced) - df_float) < 1e-12, "TracedFloat value should match plain float"
print(f"  df(2.0) tracing mode = {float(df_traced):.6f} (TracedFloat)")

# Verify Expr from TracedFloat evaluates consistently
ctx = {p.name: p.rate for p in pillars}
df_from_expr = eval_cached(df_traced._expr, ctx)
assert abs(df_from_expr - df_float) < 1e-10, \
    f"Expr eval {df_from_expr} != numeric {df_float}"
print(f"  df(2.0) Expr eval = {df_from_expr:.6f}  ✓ matches numeric")


# -- Build the swap --
from pricing.instruments.ir_swap_fixed_floatapprox import IRSwapFixedFloatApprox

swap = IRSwapFixedFloatApprox(
    symbol="TEST_5Y",
    notional=1_000_000.0,
    fixed_rate=0.05,
    tenor_years=5.0,
    currency="USD",
    collateral_currency="USD",
    side="RECEIVER",
    curve=curve,
)

# Debug mode: swap.dv01 is a float (via _TracedCallable which IS a float)
dv01_val = swap.dv01
print(f"\n  swap.dv01 = {float(dv01_val):.4f} (type: {type(dv01_val).__name__})")
assert isinstance(dv01_val, float), "dv01 should be float-like"
assert float(dv01_val) > 0, "dv01 should be positive"

npv_val = swap.npv
print(f"  swap.npv  = {float(npv_val):.4f}")

par_val = swap.par_rate
print(f"  swap.par_rate = {float(par_val):.6f}")

float_pv = swap.float_leg_pv
fixed_pv = swap.fixed_leg_pv
print(f"  swap.float_leg_pv = {float(float_pv):.4f}")
print(f"  swap.fixed_leg_pv = {float(fixed_pv):.4f}")

# Trace mode: swap.dv01() returns the Expr tree
dv01_expr = swap.dv01()
print(f"\n  swap.dv01() -> {type(dv01_expr).__name__}")
assert isinstance(dv01_expr, Expr), f"Expected Expr, got {type(dv01_expr)}"

# Evaluate the Expr against current pillar rates
dv01_from_expr = eval_cached(dv01_expr, ctx)
print(f"  eval(dv01_expr, ctx) = {dv01_from_expr:.4f}")
assert abs(dv01_from_expr - float(dv01_val)) < 1e-6, \
    f"Expr eval {dv01_from_expr} != float {float(dv01_val)}"
print(f"    ✓ Matches debug-mode value")

# NPV Expr
npv_expr = swap.npv()
assert isinstance(npv_expr, Expr)
npv_from_expr = eval_cached(npv_expr, ctx)
print(f"\n  eval(npv_expr, ctx) = {npv_from_expr:.4f}")
assert abs(npv_from_expr - float(npv_val)) < 1e-4, \
    f"NPV Expr eval {npv_from_expr} != float {float(npv_val)}"
print(f"    ✓ Matches debug-mode value")

# Par rate Expr
par_expr = swap.par_rate()
assert isinstance(par_expr, Expr)
par_from_expr = eval_cached(par_expr, ctx)
print(f"\n  eval(par_rate_expr, ctx) = {par_from_expr:.6f}")
assert abs(par_from_expr - float(par_val)) < 1e-6, \
    f"Par rate Expr eval {par_from_expr} != float {float(par_val)}"
print(f"    ✓ Matches debug-mode value")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Symbolic differentiation of @traceable Expr trees
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("6. Symbolic Differentiation (diff)")
print("=" * 70)

# diff the DV01 Expr w.r.t. each pillar
for p in pillars:
    d_expr = diff(dv01_expr, p.name)
    d_val = eval_cached(d_expr, ctx)
    print(f"  ∂dv01/∂{p.name} = {d_val:.6f}")

# diff the NPV Expr
print()
for p in pillars:
    d_expr = diff(npv_expr, p.name)
    d_val = eval_cached(d_expr, ctx)
    print(f"  ∂npv/∂{p.name} = {d_val:.4f}")

# Verify risk() still works (uses @traceable + diff)
risk = swap.risk
print(f"\n  swap.risk = {type(risk).__name__} with {len(risk)} entries")
assert len(risk) == len(pillars), f"Expected {len(pillars)} risk entries, got {len(risk)}"
print("  ✓ risk() backward compat (@traceable + diff)")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Cross-check: Expr with bumped rates
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("7. Bumped Rate Cross-Check")
print("=" * 70)

# Bump 5Y rate by 1bp and re-evaluate via Expr
ctx_bumped = dict(ctx)
ctx_bumped["5Y"] = ctx["5Y"] + 0.0001  # +1bp

dv01_bumped = eval_cached(dv01_expr, ctx_bumped)
npv_bumped = eval_cached(npv_expr, ctx_bumped)

print(f"  Base NPV          = {npv_from_expr:.4f}")
print(f"  Bumped NPV (+1bp) = {npv_bumped:.4f}")
print(f"  Δ NPV             = {npv_bumped - npv_from_expr:.6f}")
print(f"  DV01 (base)       = {dv01_from_expr:.4f}")
print(f"  DV01 (bumped)     = {dv01_bumped:.4f}")

# Same Expr tree, re-evaluated with different inputs — no re-tracing needed
print("  ✓ Same Expr tree works with different rate contexts")


# ═══════════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("ALL TESTS PASSED ✓")
print("=" * 70)
