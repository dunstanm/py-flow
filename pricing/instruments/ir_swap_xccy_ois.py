"""
ir_swap_xccy_ois.py — Cross-Currency Overnight Indexed Basis Swap (XCCY OIS)

Implements a floating-floating cross-currency swap where both legs use 
daily compounding (OIS/RFR). Supports historical fixings and the 
telescopic property for forward projections.
"""
from __future__ import annotations


import datetime
from typing import Any, Optional
from dataclasses import dataclass
from pydantic import ConfigDict
from dataclasses import field

from store import Storable
from pricing.instruments.ir_swap import IRSwapBase
from reactive.traceable import traceable
from reactive.expr import diff, Expr
from streaming import ticking
import pricing.instruments.ir_scheduling as sched


@ticking(exclude={
    "leg1_discount_curve", "leg2_discount_curve", 
    "risk", "fixings1", "fixings2"
})
@dataclass
class IRSwapXCCYOIS(Storable, IRSwapBase):
    """Cross-Currency OIS Basis Swap.
    
    Attributes
    ----------
    symbol: str
        Unique identifier.
    leg1_currency: str
        Currency of the first leg (e.g., "EUR").
    leg1_notional: float
        Notional amount in leg 1 currency.
    leg1_discount_curve: object
        Curve for discounting and OIS projection for Leg 1.
    leg1_index_name: Optional[str]
        Manual override for RFR index name (e.g., "ESTR").
    
    leg2_currency: str
        Currency of the second leg (e.g., "USD").
    leg2_notional: float
        Notional amount in leg 2 currency.
    leg2_discount_curve: object
        Curve for discounting and OIS projection for Leg 2.
    leg2_index_name: Optional[str]
        Manual override for RFR index name (e.g., "SOFR").
        
    basis_spread: float
        Spread added to Leg 1 floating rate (decimal, e.g. 0.0010 for 10bps).
    initial_fx: float
        FX rate used to convert Leg 1 to Leg 2 at initiation (Leg2 = Leg1 * FX).
    
    effective_date: datetime.date
    termination_date: datetime.date
    frequency_months: int = 12
    exchange_notional: bool = True
    
    fixings1: dict[datetime.date, float] = field(default_factory=dict, repr=False)
    fixings2: dict[datetime.date, float] = field(default_factory=dict, repr=False)
    
    evaluation_date_override: Optional[datetime.date] = None
    """
    __key__ = "symbol"
    
    symbol: str = ""
    
    # Leg 1
    leg1_currency: str = "EUR"
    leg1_notional: float = 0.0
    leg1_discount_curve: Any = field(default=None, repr=False)
    leg1_index_name: Optional[str] = None
    
    # Leg 2
    leg2_currency: str = "USD"
    leg2_notional: float = 0.0
    leg2_discount_curve: Any = field(default=None, repr=False)
    leg2_index_name: Optional[str] = None
    
    basis_spread: float = 0.0
    initial_fx: float = 1.0  # e.g. EURUSD = 1.08
    
    effective_date: Optional[datetime.date] = None
    termination_date: Optional[datetime.date] = None
    frequency_months: int = 12
    exchange_notional: bool = True
    side: str = "RECEIVER"  # RECEIVER means receive Leg 1, pay Leg 2
    
    fixings1: dict[datetime.date, float] = field(default_factory=dict, repr=False)
    fixings2: dict[datetime.date, float] = field(default_factory=dict, repr=False)
    
    evaluation_date_override: Optional[datetime.date] = None

    def __post_init__(self):
        super().__post_init__()
        # Auto-initialize notionals if only one is provided
        if self.leg2_notional == 0.0 and self.leg1_notional != 0.0:
            object.__setattr__(self, 'leg2_notional', self.leg1_notional * self.initial_fx)
        elif self.leg1_notional == 0.0 and self.leg2_notional != 0.0:
            object.__setattr__(self, 'leg1_notional', self.leg2_notional / self.initial_fx)

    @traceable
    def rfr_indices(self) -> dict[str, str]:
        """Mapping table for RFR indices."""
        return {
            "USD": "SOFR", "EUR": "ESTR", "GBP": "SONIA", "AUD": "AONIA",
            "CAD": "CORRA", "SGD": "SORA", "SGP": "SORA", "CHF": "SARON", "JPY": "TONAR"
        }

    @traceable
    def resolved_leg1_index(self) -> str:
        if self.leg1_index_name: return self.leg1_index_name
        return self.rfr_indices.get(self.leg1_currency.upper(), f"{self.leg1_currency.upper()}_OIS")

    @traceable
    def resolved_leg2_index(self) -> str:
        if self.leg2_index_name: return self.leg2_index_name
        return self.rfr_indices.get(self.leg2_currency.upper(), f"{self.leg2_currency.upper()}_OIS")

    @traceable
    def evaluation_date(self) -> datetime.date:
        if self.evaluation_date_override:
            return self.evaluation_date_override
        return datetime.date.today()

    @traceable
    def schedule(self) -> list[datetime.date]:
        if not self.effective_date or not self.termination_date:
            return []
        # Usually XCCY swaps use Leg 1's calendar or a joint calendar
        return sched.swap_schedule(
            self.effective_date, self.termination_date, 
            freq_months=self.frequency_months, 
            currency=self.leg1_currency, 
            end_of_month=True
        )

    @property
    def pillar_names(self) -> list[str]:
        names = set()
        if hasattr(self.leg1_discount_curve, "pillar_names"):
            names.update(self.leg1_discount_curve.pillar_names)
        if hasattr(self.leg2_discount_curve, "pillar_names"):
            names.update(self.leg2_discount_curve.pillar_names)
        return sorted(list(names))



    @property
    def leg1(self):
        from pricing.instruments.ir_leg import IROISLeg
        import pricing.instruments.ir_scheduling as sched
        return IROISLeg(
            currency=self.leg1_currency,
            notional=self.leg1_notional,
            projection_curve=self.leg1_discount_curve,
            schedule=self.schedule,
            evaluation_date=self.evaluation_date,
            fixings=self.fixings1,
            spread=self.basis_spread,
            exchange_notional=self.exchange_notional,
            pay_side=False
        )

    @property
    def leg2(self):
        from pricing.instruments.ir_leg import IROISLeg
        import pricing.instruments.ir_scheduling as sched
        return IROISLeg(
            currency=self.leg2_currency,
            notional=self.leg2_notional,
            projection_curve=self.leg2_discount_curve,
            schedule=self.schedule,
            evaluation_date=self.evaluation_date,
            fixings=self.fixings2,
            spread=0.0,
            exchange_notional=self.exchange_notional,
            pay_side=False
        )

    @property
    def leg_pay(self):
        leg = self.leg1 if self.side == "PAYER" else self.leg2
        leg.pay_side = True
        return leg
        
    @property
    def leg_rec(self):
        leg = self.leg2 if self.side == "PAYER" else self.leg1
        leg.pay_side = False
        return leg
        
    def discount_factor(self, currency, date):
        if currency == self.leg1_currency and self.leg1_discount_curve:
            return self.initial_fx * self.leg1_discount_curve.df(date)
        elif currency == self.leg2_currency and self.leg2_discount_curve:
            return self.leg2_discount_curve.df(date)
        return None

    @traceable
    def leg1_pv(self) -> Expr:
        """PV of Leg 1 (always positive mathematical abstraction)."""
        from reactive.expr import Sum
        if not self.leg1_discount_curve or not self.schedule:
            return 0.0
        
        # Calculate true signed cashflows then invert if it's the pay side to format as an absolute PV 
        pvs = [cf.amount * self.leg1_discount_curve.df(cf.date) for cf in self.leg1.cashflows()]
        raw_pv = Sum(pvs) if pvs else 0.0
        return raw_pv

    @traceable
    def leg2_pv(self) -> Expr:
        """PV of Leg 2 (always positive mathematical abstraction)."""
        from reactive.expr import Sum
        if not self.leg2_discount_curve or not self.schedule:
            return 0.0
            
        pvs = [cf.amount * self.leg2_discount_curve.df(cf.date) for cf in self.leg2.cashflows()]
        raw_pv = Sum(pvs) if pvs else 0.0
        return raw_pv



    @traceable
    def risk(self) -> dict[str, Expr]:
        expr = self.npv()
        if expr is None: return {}
        return {name: diff(expr, name) for name in self.pillar_names}

    def pillar_context(self) -> dict[str, Any]:
        ctx = {}
        if hasattr(self.leg1_discount_curve, 'pillar_context'):
            ctx.update(self.leg1_discount_curve.pillar_context())
        if hasattr(self.leg2_discount_curve, 'pillar_context'):
            ctx.update(self.leg2_discount_curve.pillar_context())
        return ctx
