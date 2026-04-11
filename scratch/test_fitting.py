import sys
import os
import numpy as np

project_root = os.path.abspath(os.getcwd())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Internal Imports
from pricing.marketmodels.integrated_rate_curve import IntegratedShortRateCurve, IntegratedRatePoint
from pricing.marketmodels.curve_fitter import CurveFitter
from pricing.marketmodels.yield_curve import YieldCurvePoint, LinearTermDiscountCurve
from pricing.pricing.pricing.instruments.ir_swap_fixed_floatapprox import IRSwapFixedFloatApprox
from pricing.marketmodels.swap_curve import SwapQuote

print("Building curve and fitter...")

# Setup similar to the sandbox
tenors = [1.0, 2.0, 5.0, 10.0, 30.0]
rates = [0.045, 0.042, 0.0385, 0.037, 0.0365]

quotes = [
    SwapQuote(symbol=f"QUOTE_{t}Y", tenor=float(t), rate=r)
    for t, r in zip(tenors, rates)
]

points = [
    YieldCurvePoint(name=f"PT_{t}Y", tenor_years=t, is_fitted=True)
    for t in tenors
]

curve = IntegratedShortRateCurve(
    name="test_curve", 
    currency="USD", 
    points=points, 
    degree=2, 
    is_local=False
)

# Link quotes to points
for pt, q in zip(points, quotes):
    pt.quote_ref = q

target_swaps = [
    IRSwapFixedFloatApprox(
        symbol=f"SWAP_{int(q.tenor)}Y",
        tenor_years=q.tenor,
        fixed_rate=q.rate,
        curve=curve,
        notional=10e6
    ) for q in quotes
]

fitter = CurveFitter(
    name="TEST_FITTER",
    curve=curve,
    points=points,
    quotes=quotes,
    target_swaps=target_swaps
)

print("Starting solve...")
import time
start = time.time()
fitter.solve()
print(f"Solve complete in {(time.time() - start)*1000:.2f}ms")

# Verify residuals
print("\nResiduals (NPV/Notional):")
for s in target_swaps:
    print(f"  {s.symbol}: {s.npv/s.notional:.2e}")

# Verify curve shape
print("\nForward Rates:")
t_check = [0.5, 1.5, 3.0, 7.5, 15.0, 25.0]
fwds = curve.fwd_array(t_check)
for t, f in zip(t_check, fwds):
    print(f"  {t}Y: {f*100:.4f}%")
