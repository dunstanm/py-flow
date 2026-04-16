"""
ir_swap_fixed_ois.py — Multi-Currency Overnight Indexed Swap (OIS)

Implements the standard Overnight Indexed Swap using daily compounding on the floating leg.
Supports major RFRs (SOFR, ESTR, SONIA, etc.) with automatic index resolution based on currency.

Supports:
1.  Aged periods (uses historical fixings).
2.  Future periods (uses telescopic property/approximation).
3.  Calendar-aware scheduling via ir_scheduling.py.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from store import Storable
from reactive.traceable import traceable
from reactive.computed import effect
from reactive.expr import diff, Expr
from streaming import ticking
import pricing.instruments.ir_scheduling as sched
from pricing.instruments.base import Instrument

@ticking(exclude={"discount_curve", "risk_ladder", "fixings", "pillar_names"})
@dataclass
class IRSwapFixedOIS(Instrument):
    """Multi-Currency Overnight Indexed Swap (OIS).
    
    Attributes
    ----------
    symbol: str
        Unique identifier.
    notional: float
        Principal amount.
    fixed_rate: float
        Fixed coupon rate (decimal, e.g. 0.05).
    effective_date: datetime.date
        Start of the first accrual period.
    termination_date: datetime.date
        Maturity of the swap.
    frequency_months: int
        Payment frequency (standard OIS is 12).
    side: str
        "RECEIVER" (receives fixed) or "PAYER" (pays fixed).
    currency: str
        ISO currency code (e.g., USD, EUR, GBP).
    discount_curve: object
        Curve providing .df(target_date) for discounting and index projection.
    fixings: dict[datetime.date, float]
        Historical daily fixing rates (index depends on currency).
    """
    __key__ = "symbol"
    
    symbol: str = ""
    notional: float = 0.0
    fixed_rate: float = 0.0
    effective_date_override: Optional[datetime.date] = None
    termination_date_override: Optional[datetime.date] = None
    tenor_years: float = 0.0
    frequency_months: int = 12
    side: str = "RECEIVER"
    currency: str = "USD"
    is_target: bool = False
    
    discount_curve: object = field(default=None, repr=False)
    fixings: dict[datetime.date, float] = field(default_factory=dict, repr=False)
    
    evaluation_date_override: Optional[datetime.date] = None

    @traceable
    def index_name(self) -> str:
        """Map currency to its corresponding Overnight Index."""
        mapping = {
            "USD": "SOFR",
            "EUR": "ESTR",
            "GBP": "SONIA",
            "AUD": "AONIA",
            "CAD": "CORRA",
            "SGD": "SORA",
            "SGP": "SORA", # User requested SGP
            "CHF": "SARON",
            "JPY": "TONAR"
        }
        return mapping.get(self.currency.upper(), f"{self.currency.upper()}_OIS")

    @traceable
    def effective_date(self) -> datetime.date:
        """Effective date (start of swap). Uses override or evaluation date."""
        if self.effective_date_override:
            return self.effective_date_override
        return self.evaluation_date

    @traceable
    def termination_date(self) -> datetime.date:
        """Termination date (end of swap). Uses override or effective_date + tenor."""
        if self.termination_date_override:
            return self.termination_date_override
        # Add tenor_years to effective_date. Rough approx is fine for demo
        days = int(self.tenor_years * 365.2425)
        return self.effective_date + datetime.timedelta(days=days)

    @traceable
    def evaluation_date(self) -> datetime.date:
        if self.evaluation_date_override:
            return self.evaluation_date_override
        return datetime.date.today()

    @traceable
    def schedule(self) -> list[datetime.date]:
        """Generate the calendar-aware date schedule."""
        if not self.effective_date or not self.termination_date:
            return []
        
        return sched.swap_schedule(
            self.effective_date,
            self.termination_date,
            freq_months=self.frequency_months,
            currency=self.currency,
            end_of_month=True
        )

    def _tenor(self, date: datetime.date) -> float:
        """Helper to get tenor in years from evaluation date."""
        if not self.evaluation_date:
            return 0.0
        return (date - self.evaluation_date).days / 365.2425

    @traceable
    def fixed_leg_pv(self) -> Expr:
        """PV of fixed leg = Σ [notional * rate * tau * df_end]"""
        if not self.discount_curve or not self.schedule:
            return 0.0
        
        sch = self.schedule
        dcc = sched.DayCountConvention.Thirty360US
        pvs = []
        for i in range(len(sch) - 1):
            end = sch[i+1]
            tau = sched.year_fraction(sch[i], end, dcc)
            df = self.discount_curve.df(self._tenor(end))
            pvs.append(self.notional * self.fixed_rate * tau * df)
        return sum(pvs)

    @traceable
    def float_leg_pv(self) -> Expr:
        """PV of floating leg using OIS compounding (with telescopic approx)."""
        if not self.discount_curve or not self.schedule:
            return 0.0
        
        sch = self.schedule
        pvs = []
        for i in range(len(sch) - 1):
            start = sch[i]
            end = sch[i+1]
            tau = sched.year_fraction(start, end, sched.DayCountConvention.Act360)
            
            rate = sched.compounded_rate(
                start, 
                end, 
                evaluation_date=self.evaluation_date,
                fixings=self.fixings,
                discount_curve=self.discount_curve,
                telescopic=True,
                day_counter=sched.DayCountConvention.Act360
            )
            df_end = self.discount_curve.df(self._tenor(end))
            pvs.append(self.notional * rate * tau * df_end)
        return sum(pvs)

    @traceable
    def npv(self) -> Expr:
        """NPV = Fixed - Float (RECEIVER) or Float - Fixed (PAYER)."""
        if self.side == "PAYER":
            return self.float_leg_pv - self.fixed_leg_pv
        return self.fixed_leg_pv - self.float_leg_pv

    @traceable
    def dv01(self) -> Expr:
        """DV01: Approximation via fixed leg annuity."""
        if not self.discount_curve or not self.schedule:
            return 0.0
        
        sch = self.schedule
        dcc = sched.DayCountConvention.Thirty360US
        
        terms = []
        for i in range(len(sch) - 1):
            start, end = sch[i], sch[i+1]
            tau = sched.year_fraction(start, end, dcc)
            df = self.discount_curve.df(self._tenor(end))
            terms.append(self.notional * tau * df * 0.0001)
            
        return sum(terms) if terms else 0.0

    @traceable
    def par_rate(self) -> Expr:
        """The fixed rate that would make the current NPV zero."""
        if not self.schedule:
            return 0.0
            
        sch = self.schedule
        dcc = sched.DayCountConvention.Thirty360US
        annuity_terms = []
        for i in range(len(sch) - 1):
            start, end = sch[i], sch[i+1]
            tau = sched.year_fraction(start, end, dcc)
            df = self.discount_curve.df(self._tenor(end))
            annuity_terms.append(self.notional * tau * df)
            
        annuity = sum(annuity_terms)
        return self.float_leg_pv / annuity if annuity_terms else 0.0

    @traceable
    def risk_ladder(self) -> dict[str, Expr]:
        """∂npv/∂pillar_rate."""
        expr = self.npv()
        if expr is None: return {}
        return {
            name: diff(expr, name)
            for name in self.pillar_names
        }

    @traceable
    def pnl_status(self) -> str:
        val = self.npv
        if val > 0:
            return "PROFIT"
        elif val < 0:
            return "LOSS"
        return "FLAT"

    @effect("npv")
    def on_npv(self, value):
        import pricing.marketmodels.ir_curve_fitter
        if pricing.marketmodels.ir_curve_fitter.IS_SOLVING or getattr(self, "is_target", False):
            return
        if hasattr(self, "tick"):
            self.tick()
