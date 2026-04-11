"""
equity_forward — Single stock forward.
"""
from dataclasses import field
from pydantic.dataclasses import dataclass
from pydantic import ConfigDict

from store.base import Storable
from reactive.traceable import traceable
from streaming.decorator import ticking

@ticking(exclude={"discount_curve", "dividend_curve"})
@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class EquityForward(Storable):
    """
    Pricing model for a single stock forward.
    Uses continuous dividend yields.
    
    Forward Price F = S * e^{(r - q) * t}
    """
    __key__ = "symbol"
    
    symbol: str = ""
    spot_price: float = 0.0
    strike_price: float = 0.0
    tenor_years: float = 0.0
    notional_shares: float = 0.0
    
    discount_curve: object = None 
    dividend_curve: object = None 

    @traceable
    def forward_price(self) -> float:
        """Calculates the theoretical forward stock price F_t."""
        if not self.discount_curve or not self.dividend_curve:
            return self.spot_price
        
        # F = S * (DF_dividend / DF_risk_free)
        df_r = self.discount_curve.df(self.tenor_years)
        df_q = self.dividend_curve.df(self.tenor_years)
        
        if df_r == 0:
            return 0.0
        return self.spot_price * (df_q / df_r)

    @traceable
    def npv(self) -> float:
        """Calculates the NPV of the long forward position."""
        if not self.discount_curve:
            return 0.0
            
        fwd = self.forward_price()
        df_r = self.discount_curve.df(self.tenor_years)
        
        # PV = DF_r * (F - K) * Shares
        return df_r * (fwd - self.strike_price) * self.notional_shares
