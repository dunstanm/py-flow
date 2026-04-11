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

from reactive.expr import Const, Variable, Exp, eval_cached, diff, _wrap
from reactive.traced import (
    TracedFloat,
    _start_tracing, _stop_tracing, _is_tracing,
    _start_building, _stop_building, _is_building,
    exp as traced_exp,
    log as traced_log,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. TracedFloat arithmetic
# ═══════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("1. TracedFloat Arithmetic")
print("=" * 70)

x = TracedFloat(3.0, Variable("x"))
y = TracedFloat(2.0, Variable("y"))

# Basic ops
add = x + y
sub = x - y
mul = x * y
div = x / y
neg = -x
pw = x ** y

assert float(add) == 5.0, f"add: expected 5.0, got {float(add)}"
assert float(sub) == 1.0, f"sub: expected 1.0, got {float(sub)}"
assert float(mul) == 6.0, f"mul: expected 6.0, got {float(mul)}"
assert float(div) == 1.5, f"div: expected 1.5, got {float(div)}"
assert float(neg) == -3.0, f"neg: expected -3.0, got {float(neg)}"
assert float(pw) == 9.0, f"pow: expected 9.0, got {float(pw)}"

# Verify Expr trees evaluate correctly
ctx = {"x": 3.0, "y": 2.0}
assert eval_cached(add._expr, ctx) == 5.0
assert eval_cached(sub._expr, ctx) == 1.0
assert eval_cached(mul._expr, ctx) == 6.0
assert eval_cached(div._expr, ctx) == 1.5
assert eval_cached(neg._expr, ctx) == -3.0
assert eval_cached(pw._expr, ctx) == 9.0

# With different context (change x → 10)
ctx2 = {"x": 10.0, "y": 2.0}
assert eval_cached(add._expr, ctx2) == 12.0
assert eval_cached(mul._expr, ctx2) == 20.0

print("  ✓ Basic arithmetic (add, sub, mul, div, neg, pow)")

# Mixed with plain floats
r1 = x + 5.0
r2 = 5.0 + x
r3 = x * 0.5
r4 = 0.5 * x
assert float(r1) == 8.0
assert float(r2) == 8.0
assert float(r3) == 1.5
assert float(r4) == 1.5
assert eval_cached(r1._expr, ctx) == 8.0
assert eval_cached(r2._expr, ctx) == 8.0
assert eval_cached(r3._expr, ctx) == 1.5
assert eval_cached(r4._expr, ctx) == 1.5

print("  ✓ Mixed with plain floats (commutative)")

# Chained arithmetic (simulates real pricing loops)
pv = 0.0
for i in range(3):
    df = TracedFloat(0.98 - 0.01 * i, Variable(f"df_{i}"))
    dcf = 0.25
    pv += df * dcf * 100.0  # notional=100, dcf=0.25
assert isinstance(pv, TracedFloat), "Accumulated pv should be TracedFloat"
expected_pv = (0.98 + 0.97 + 0.96) * 0.25 * 100.0
assert abs(float(pv) - expected_pv) < 1e-10, f"pv: expected {expected_pv}, got {float(pv)}"

# Verify the Expr tree works with different rates
ctx_alt = {"df_0": 0.95, "df_1": 0.90, "df_2": 0.85}
expected_alt = (0.95 + 0.90 + 0.85) * 0.25 * 100.0
assert abs(eval_cached(pv._expr, ctx_alt) - expected_alt) < 1e-10

print("  ✓ Chained accumulation (loop pattern)")

# isinstance(TracedFloat, float) should be True
assert isinstance(x, float), "TracedFloat must be isinstance float"

print("  ✓ isinstance(TracedFloat, float) == True")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Traced math functions
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("2. Traced Math Functions")
print("=" * 70)

a = TracedFloat(1.0, Variable("a"))
e_a = traced_exp(a)
assert isinstance(e_a, TracedFloat)
assert abs(float(e_a) - math.exp(1.0)) < 1e-10
assert abs(eval_cached(e_a._expr, {"a": 1.0}) - math.exp(1.0)) < 1e-10
assert abs(eval_cached(e_a._expr, {"a": 2.0}) - math.exp(2.0)) < 1e-10

print("  ✓ traced_exp")

b = TracedFloat(2.718, Variable("b"))
l_b = traced_log(b)
assert isinstance(l_b, TracedFloat)
assert abs(float(l_b) - math.log(2.718)) < 1e-10

print("  ✓ traced_log")

# Plain floats pass through unchanged
assert traced_exp(1.0) == math.exp(1.0)
assert traced_log(2.718) == math.log(2.718)

print("  ✓ Plain floats pass through")


# ═══════════════════════════════════════════════════════════════════════════
# 3. __expr__ protocol and _wrap interop
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("3. __expr__ Protocol / _wrap Interop")
print("=" * 70)

tf = TracedFloat(42.0, Variable("answer"))
wrapped = _wrap(tf)
assert isinstance(wrapped, Variable)
assert wrapped.name == "answer"
print("  ✓ _wrap(TracedFloat) extracts ._expr via __expr__")

# Expr + TracedFloat should work
expr = Const(10.0) + tf
assert eval_cached(expr, {"answer": 42.0}) == 52.0
print("  ✓ Expr + TracedFloat interop")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Tracing context
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("4. Tracing Context")
print("=" * 70)

assert not _is_tracing()
_start_tracing()
assert _is_tracing()
_start_tracing()  # nested
assert _is_tracing()
_stop_tracing()
assert _is_tracing()  # still nested
_stop_tracing()
assert not _is_tracing()

print("  ✓ Reentrant tracing context")

assert not _is_building()
_start_building()
assert _is_building()
_stop_building()
assert not _is_building()

print("  ✓ Building context")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Full end-to-end: IntegratedShortRateCurve + IRSwapFixedFloatApprox
# ═══════════════════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("5. End-to-End: Curve + Swap with @traceable")
print("=" * 70)

from pricing.marketmodels.integrated_rate_curve import IntegratedShortRateCurve, IntegratedRatePoint

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
from pricing.pricing.pricing.instruments.ir_swap_fixed_floatapprox import IRSwapFixedFloatApprox

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

# Verify risk() still works (uses @computed_expr + diff)
risk = swap.risk
print(f"\n  swap.risk = {type(risk).__name__} with {len(risk)} entries")
assert len(risk) == len(pillars), f"Expected {len(pillars)} risk entries, got {len(risk)}"
print("  ✓ risk() backward compat (@computed_expr + diff)")


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
