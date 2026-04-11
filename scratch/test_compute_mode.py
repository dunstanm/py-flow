"""
Verify the full import chain for the curve fitting sandbox works
in standalone compute-library mode — no warnings, no mocks, no DH.
"""
import sys
import os
import time

project_root = os.path.abspath(os.getcwd())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("=== Import test ===")
t0 = time.time()

# These are the exact imports from curve_fitting_sandbox.py
from pricing.marketmodels.integrated_rate_curve import IntegratedShortRateCurve, IntegratedRatePoint
from pricing.marketmodels.curve_fitter import CurveFitter
from pricing.marketmodels.yield_curve import YieldCurvePoint, LinearTermDiscountCurve
from pricing.pricing.pricing.instruments.ir_swap_fixed_floatapprox import IRSwapFixedFloatApprox
from pricing.marketmodels.swap_curve import SwapQuote

print(f"All imports loaded in {(time.time()-t0)*1000:.0f}ms")

# Verify @ticking is a no-op — classes should have tick() as a no-op
pt = YieldCurvePoint(name="test", tenor_years=5.0)
pt.tick()  # Should be silent no-op
print(f"YieldCurvePoint.tick() = {pt.tick.__name__}")  # Should be _tick_noop

# Verify streaming is NOT active
from streaming.decorator import _streaming_active
print(f"Streaming active: {_streaming_active}")  # Should be False

# Full curve fitting test
import numpy as np

tenors = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 12.0, 15.0, 20.0, 30.0]
rates  = [0.0450, 0.0420, 0.0405, 0.0385, 0.0375, 0.0370, 0.0372, 0.0375, 0.0380, 0.0365]

quotes = [SwapQuote(symbol=f"Q_{int(t)}Y", tenor=t, rate=r) for t, r in zip(tenors, rates)]
points = [YieldCurvePoint(name=f"PT_{int(t)}Y", tenor_years=t, is_fitted=True) for t in tenors]

curve = IntegratedShortRateCurve(
    name="sandbox", currency="USD", points=points, degree=2, is_local=False
)
for pt, q in zip(points, quotes):
    pt.quote_ref = q

swaps = [
    IRSwapFixedFloatApprox(
        symbol=f"SWAP_{int(q.tenor)}Y", tenor_years=q.tenor,
        fixed_rate=q.rate, curve=curve, notional=10e6
    ) for q in quotes
]

fitter = CurveFitter(
    name="SANDBOX", curve=curve, points=points, quotes=quotes, target_swaps=swaps
)

print(f"\n=== Solving {len(tenors)}-pillar curve ===")
t0 = time.time()
fitter.solve()
ms = (time.time()-t0)*1000
print(f"Done in {ms:.0f}ms")

# Check residuals
max_resid = max(abs(s.npv/s.notional) for s in swaps)
print(f"Max residual: {max_resid:.2e}")
assert max_resid < 1e-8, f"Solve failed: max residual {max_resid}"
print("\n✓ All tests passed — pure compute library, no streaming required.")
