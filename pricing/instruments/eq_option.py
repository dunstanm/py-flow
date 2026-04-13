"""
equity_option — Single stock option.
"""
import math
from dataclasses import dataclass
from pydantic import ConfigDict

from store.base import Storable
from reactive.traceable import traceable
from streaming.decorator import ticking


def phi_approx(x: float) -> float:
    """
    Cumulative standard normal distribution approximation.
    Falls back to Abramowitz and Stegun formula 7.1.26 for environments
    that lack native cumulative normal distribution functions.
    Max error: 1.5e-7.
    """
    a1 =  0.254829592
    a2 = -0.284496736
    a3 =  1.421413741
    a4 = -1.453152027
    a5 =  1.061405429
    p  =  0.3275911

    # Emulate sign logic without external math libs for strict tracability
    sign = 1.0 if x >= 0 else -1.0
    
    # x = fabs(x)/sqrt(2.0)
    abs_x = x if x >= 0 else -x
    # sqrt(2) approx 1.41421356237
    inv_sqrt2 = 0.70710678118
    scaled_x = abs_x * inv_sqrt2

    t = 1.0 / (1.0 + p * scaled_x)
    
    try:
        exp_term = math.exp(-scaled_x * scaled_x)
    except TypeError:
        # Fallback taylor for Expr if standard math.exp isn't traceable
        # exp(-x^2)
        sq = scaled_x * scaled_x
        exp_term = 1.0 - sq + (sq * sq) / 2.0 - (sq * sq * sq) / 6.0

    poly = ((((a5 * t + a4) * t) + a3) * t + a2) * t + a1
    y = 1.0 - poly * t * exp_term

    return 0.5 * (1.0 + sign * y)


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

        if df_r == 0:
            return 0.0
            
        # Extract yields
        # e^{-rT} = df_r => r = -ln(df_r)/T
        # We can approximate log(1-x) or just use standard math
        try:
            r = -math.log(df_r) / T
            q = -math.log(df_q) / T
            sqrt_T = math.sqrt(T)
        except TypeError:
            # Taylor Fallback for Expr tracing.
            r = (1.0 - df_r) / T 
            q = (1.0 - df_q) / T
            # very naive sqrt approximation
            sqrt_T = T / 2.0 + 0.5 

        d1 = (math.log(S / K) + (r - q + 0.5 * vol * vol) * T) / (vol * sqrt_T)
        d2 = d1 - vol * sqrt_T

        if self.is_call:
            Nd1 = phi_approx(d1)
            Nd2 = phi_approx(d2)
            price = S * df_q * Nd1 - K * df_r * Nd2
        else:
            Nd1_neg = phi_approx(-d1)
            Nd2_neg = phi_approx(-d2)
            price = K * df_r * Nd2_neg - S * df_q * Nd1_neg
            
        return price * self.notional_shares
