"""
equity_option — Single stock option.
"""
from dataclasses import dataclass

from store.base import Storable
from reactive.traceable import traceable
from streaming.decorator import ticking
from pricing.maths.black import black_scholes_formula

@ticking(exclude={"discount_curve", "dividend_curve"})
@dataclass
class EquityOption(Storable):
    """
    Pricing model for a European single stock option.
    Uses Black-Scholes-Merton with continuous dividends.
    """
    __key__ = "symbol"
    
    symbol: str = ""
    is_call: bool = True
    spot_price: float = 0.0
    strike_price: float = 0.0
    tenor_years: float = 0.0
    volatility: float = 0.0
    notional_shares: float = 0.0
    
    discount_curve: object = None 
    dividend_curve: object = None

    @traceable
    def npv(self) -> float:
        if not self.discount_curve or not self.dividend_curve or self.tenor_years <= 0 or self.volatility <= 0:
            return 0.0
            
        S = self.spot_price
        K = self.strike_price
        T = self.tenor_years
        vol = self.volatility
        
        df_r = self.discount_curve.df(T)
        df_q = self.dividend_curve.df(T)

        price = black_scholes_formula(self.is_call, S, K, T, vol, df_r, df_q)
            
        return price * self.notional_shares
