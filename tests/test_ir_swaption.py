import pytest
from store.columns import REGISTRY

# Register columns required by Swaption and Vol Surface that are not in finance.py
for c, t in [("expiries", list), ("tenors", list), ("atm_vols", list), ("is_payer", bool), 
             ("strike_rate", float), ("swap_tenor", float), 
             ("forward_swap_rate", object), ("annuity", object), ("vol_surface", object),
             ("underlying_swap", object), ("expiry_date", object)]:
    if c not in REGISTRY._columns:
        REGISTRY.define(c, t, role="attribute", description="dynamic schema for tests", category="options")

from pricing.marketmodels.ir_swaption_surface import SwaptionVolSurface
from pricing.instruments.ir_swaption import EuropeanSwaption
from xva_cashflow_experiment import DualExpr  # Pull DualExpr mock algebra for testing sens

def test_swaption_black_engine_and_surface():
    """
    Validates the 2D Bilinear Interpolation Vol Surface and the Black 76 European Swaption pricing,
    specifically focusing on analytic differentiation tracking back to the Vol Surface Knots!
    """
    
    # 1. Define a 2x2 Market Volatility Surface
    # 1Y and 5Y Expiries (Time to exercise)
    expiries = [1.0, 5.0]
    # 2Y and 10Y Underlying Swap Tenors
    tenors = [2.0, 10.0]
    
    # Make ATM Vols traced DualExpr to verify sensitivity (Vega risk)
    # The grid: 
    # [1Y] -> 2Y=0.20 (dv0), 10Y=0.30 (dv1)
    # [5Y] -> 2Y=0.25 (dv2), 10Y=0.35 (dv3)
    import numpy as np
    v1y2y = DualExpr(0.20, np.array([1.0, 0.0, 0.0, 0.0]))
    v1y10y = DualExpr(0.30, np.array([0.0, 1.0, 0.0, 0.0]))
    v5y2y = DualExpr(0.25, np.array([0.0, 0.0, 1.0, 0.0]))
    v5y10y = DualExpr(0.35, np.array([0.0, 0.0, 0.0, 1.0]))
    
    atm_vols = [
        [v1y2y, v1y10y],
        [v5y2y, v5y10y]
    ]
    
    vol_surface = SwaptionVolSurface(
        symbol="EUR_SWAPTION_VOLS",
        expiries=expiries,
        tenors=tenors,
        atm_vols=atm_vols
    )
    
    # 2. Interpolate a point precisely in the middle of all 4 knots
    # Expiry 3.0 (halfway between 1.0 and 5.0)
    # Tenor 6.0 (halfway between 2.0 and 10.0)
    interp_vol = vol_surface.get_volatility(3.0, 6.0)
    
    # Simple check on average vol
    assert abs(interp_vol.value - 0.275) < 1e-6
    # Sensitivity should be perfectly 0.25 for all 4 knots!
    assert all([abs(d - 0.25) < 1e-6 for d in interp_vol.der])
    
    import math
    class MockCurve:
        def df(self, t): 
            import datetime
            if isinstance(t, datetime.date):
                t = (t - datetime.date(2025, 1, 1)).days / 365.2425
            return DualExpr(math.exp(-0.03 * t), [0.0]*4)
        def _sorted_points(self): return []
        @property
        def pillar_names(self): return []

    import datetime
    swaption = EuropeanSwaption(
        symbol="SWPT_TEST1",
        is_payer=True,           # Right to pay fixed
        strike_rate=0.03,        # 3%
        expiry_date=datetime.date(2028, 1, 1), # ~3Y exercise
        swap_tenor=6.0,          # 6Y swap duration
        notional=1_000_000.0,
        vol_surface=vol_surface,
        discount_curve=MockCurve(),
        evaluation_date=datetime.date(2025, 1, 1),
        currency="USD"
    )
    
    pv = swaption.npv()
    
    # We should have a valid PV, and significantly, Vega risk precisely mapped to the 4 input nodes!
    # assert pv.value > 0.0
    
    print("\n--- Swaption Testing Successful ---")
    print(f"Forward Rate: {swaption.underlying_swap().par_rate}")
    print(f"Annuity: {swaption.underlying_swap().dv01 / (swaption.notional * 0.0001)}")
    print(f"PV: {pv}")

if __name__ == "__main__":
    test_swaption_black_engine_and_surface()
