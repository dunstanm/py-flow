"""
dividend_curve — Market model for equity dividend forecasting.

Supports continuous dividend yield models as a first pass for Black-Scholes.
"""
from store.base import Storable
from reactive.traceable import traceable
from dataclasses import dataclass

@dataclass
class DividendYieldCurve(Storable):
    """
    Continuous dividend yield curve for pricing equity derivatives.
    For single stock options under classical Black-Scholes without discrete jumps.
    """
    __key__ = "symbol"
    
    symbol: str = ""
    continuous_yield: float = 0.0
    
    @traceable
    def yield_at(self, t: float) -> float:
        """Returns the continuous annualized dividend yield at time t."""
        return self.continuous_yield
    
    @traceable
    def df(self, t: float) -> float:
        """Returns the dividend discount factor e^(-q * t)."""
        # Using a simple Taylor series or math.exp if supported by Expr
        # For traceable, standard math module exp works natively on plain floats, 
        # but to ensure strict Expr compatibility we can use Taylor or wait for engine support.
        # Here we use naive continuous discounting for simplicity.
        import math
        try:
            return math.exp(-self.continuous_yield * t)
        except TypeError:
            # Fallback if tracer doesn't support math.exp natively yet
            q = self.continuous_yield
            # exp(-x) ~ 1 - x + x^2/2 - x^3/6
            x = (q * t)
            return 1.0 - x + (x * x) / 2.0 - (x * x * x) / 6.0
