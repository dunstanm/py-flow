"""
pricing.marketmodels.fx_spot — Live FX spot rate and derived market data quotes.
"""
from __future__ import annotations
from dataclasses import dataclass

from store.base import Storable
from reactive.traceable import traceable
from reactive.computed import effect
from streaming.decorator import ticking
from pricing.marketmodels.ir_curve_swap import SwapQuote

@ticking
@dataclass
class FXSpot(Storable):
    """Live FX spot rate.  @effect pushes every mid change to DH."""
    __key__ = "pair"

    pair: str = ""
    bid: float = 0.0
    ask: float = 0.0
    currency: str = ""

    @traceable
    def mid(self):
        return (self.bid + self.ask) / 2

    @traceable
    def spread_pips(self):
        return (self.ask - self.bid) * 10000

    @effect("mid")
    def on_mid(self, value):
        self.tick()


@ticking(exclude={"fx_ref", "fx_base_mid", "base_rate", "sensitivity"})
@dataclass
class FXLinkedSwapQuote(SwapQuote):
    """A SwapQuote whose rate shifts dynamically based on an FX Spot pair."""
    fx_ref: object = None
    fx_base_mid: float = 0.0
    sensitivity: float = 0.5
    base_rate: float = 0.0

    @traceable
    def rate(self):
        if self.fx_ref is None or self.fx_base_mid == 0.0:
            return self.base_rate
        # Calculate percentage shift in the reference fx pair
        pct_move = (self.fx_ref.mid - self.fx_base_mid) / self.fx_base_mid
        # Shift the quote's base rate correspondingly
        return max(0.0001, self.base_rate + self.sensitivity * pct_move)
