import datetime
from typing import List
from dataclasses import dataclass
from store.base import Storable
from reactive.traceable import traceable

@dataclass
class SwaptionVolSurface(Storable):
    """
    A 2D Volatility Surface for Swaptions.
    Bilinear interpolation across Expiry (Option Time) and Tenor (Swap Length).
    Implicitly propagates AAD risk to the 4 nearest knots because arithmetic
    is executed natively in Python using the DualExpr/TracedFloat system.
    """
    __key__ = "symbol"
    
    symbol: str
    expiries: List[float]  # y-axis (time to exercise)
    tenors: List[float]    # x-axis (length of underlying swap)
    atm_vols: List[List[float]]  # 2D Grid [expiry_idx][tenor_idx]
    
    from typing import Optional
    base_date: Optional[datetime.date] = None
    
    def get_volatility(self, expiry, tenor: float) -> float:
        if isinstance(expiry, datetime.date):
            b_date = self.base_date or datetime.date.today()
            expiry_t = (expiry - b_date).days / 365.2425
        else:
            expiry_t = float(expiry)
            
        # Edge cases: Flat extrapolation outside the grid
        e_clamped = max(self.expiries[0], min(expiry_t, self.expiries[-1]))
        t_clamped = max(self.tenors[0], min(tenor, self.tenors[-1]))
        
        # Locate indices for bounding box (x1, x2, y1, y2)
        # Assuming sorted lists
        def find_knot(val, arr):
            for i in range(len(arr) - 1):
                if val <= arr[i+1]:
                    return i
            return len(arr) - 2 # Should not happen due to clamp

        i_e = find_knot(e_clamped, self.expiries)
        i_t = find_knot(t_clamped, self.tenors)
        
        e1, e2 = self.expiries[i_e], self.expiries[i_e+1]
        t1, t2 = self.tenors[i_t], self.tenors[i_t+1]
        
        # 4 knots
        v11 = self.atm_vols[i_e][i_t]       # bottom-left
        v12 = self.atm_vols[i_e][i_t+1]     # bottom-right
        v21 = self.atm_vols[i_e+1][i_t]     # top-left
        v22 = self.atm_vols[i_e+1][i_t+1]   # top-right
        
        # Linear interpolation fractions
        e_frac = (e_clamped - e1) / (e2 - e1) if e2 > e1 else 0.0
        t_frac = (t_clamped - t1) / (t2 - t1) if t2 > t1 else 0.0
        
        # Interpolate across tenors (x-axis) for both expiries
        vol_e1 = v11 + t_frac * (v12 - v11)
        vol_e2 = v21 + t_frac * (v22 - v21)
        
        # Interpolate across expiries (y-axis)
        final_vol = vol_e1 + e_frac * (vol_e2 - vol_e1)
        
        return final_vol
