from __future__ import annotations
import datetime
from dataclasses import dataclass
from typing import Any, Optional

from reactive.expr import Sum, Expr
from pricing.instruments.cashflow import CashFlow
import pricing.instruments.ir_scheduling as sched

class IRLeg:
    """Base class for Interest Rate Swap Legs emitting CashFlows."""
    def cashflows(self) -> list[CashFlow]:
        raise NotImplementedError

@dataclass
class IRFixedLeg(IRLeg):
    currency: str
    notional: float
    fixed_rate: float
    schedule: list[datetime.date]
    day_counter: sched.DayCountConvention = sched.DayCountConvention.Thirty360US
    exchange_notional: bool = False
    pay_side: bool = False

    def cashflows(self) -> list[CashFlow]:
        cfs = []
        mult = -1.0 if self.pay_side else 1.0
        
        # Notional Exchange: Start
        if self.exchange_notional and len(self.schedule) > 0:
            cfs.append(CashFlow(self.schedule[0], mult * -1.0 * self.notional, self.currency, is_notional=True))
            
        for i in range(len(self.schedule) - 1):
            start, end = self.schedule[i], self.schedule[i+1]
            tau = sched.year_fraction(start, end, self.day_counter)
            amount = self.fixed_rate * tau * self.notional * mult
            cfs.append(CashFlow(end, amount, self.currency))
            
        # Notional Exchange: End
        if self.exchange_notional and len(self.schedule) > 0:
            cfs.append(CashFlow(self.schedule[-1], mult * self.notional, self.currency, is_notional=True))
            
        return cfs

@dataclass
class IRFloatLeg(IRLeg):
    """Explicit Fwd-rate floating leg."""
    currency: str
    notional: float
    projection_curve: Any
    schedule: list[datetime.date]
    spread: float = 0.0
    day_counter: sched.DayCountConvention = sched.DayCountConvention.Act360
    exchange_notional: bool = False
    pay_side: bool = False

    def cashflows(self) -> list[CashFlow]:
        cfs = []
        mult = -1.0 if self.pay_side else 1.0
        
        if self.exchange_notional and len(self.schedule) > 0:
            cfs.append(CashFlow(self.schedule[0], mult * -1.0 * self.notional, self.currency, is_notional=True))

        for i in range(len(self.schedule) - 1):
            start, end = self.schedule[i], self.schedule[i+1]
            tau = sched.year_fraction(start, end, self.day_counter)
            
            # rate logic
            if self.projection_curve:
                rate = self.projection_curve.fwd(start, end) + self.spread
            else:
                rate = self.spread
                
            amount = rate * tau * self.notional * mult
            cfs.append(CashFlow(end, amount, self.currency))

        if self.exchange_notional and len(self.schedule) > 0:
            cfs.append(CashFlow(self.schedule[-1], mult * self.notional, self.currency, is_notional=True))
            
        return cfs

@dataclass
class IROISLeg(IRLeg):
    """OIS Compounded Leg."""
    currency: str
    notional: float
    projection_curve: Any # we use discount_curve inherently for OIS projection conventionally
    schedule: list[datetime.date]
    evaluation_date: datetime.date
    spread: float = 0.0
    fixings: dict = None
    exchange_notional: bool = False
    pay_side: bool = False

    def cashflows(self) -> list[CashFlow]:
        cfs = []
        mult = -1.0 if self.pay_side else 1.0
        fix = self.fixings or {}
        
        if self.exchange_notional and len(self.schedule) > 0:
            cfs.append(CashFlow(self.schedule[0], mult * -1.0 * self.notional, self.currency, is_notional=True))

        for i in range(len(self.schedule) - 1):
            start, end = self.schedule[i], self.schedule[i+1]
            tau = sched.year_fraction(start, end, sched.DayCountConvention.Act360)
            
            rate = sched.compounded_rate(
                start, end, 
                evaluation_date=self.evaluation_date, 
                fixings=fix, 
                discount_curve=self.projection_curve, 
                telescopic=True, 
                day_counter=sched.DayCountConvention.Act360
            )
            
            amount = (rate + self.spread) * tau * self.notional * mult
            cfs.append(CashFlow(end, amount, self.currency))
            
        if self.exchange_notional and len(self.schedule) > 0:
            cfs.append(CashFlow(self.schedule[-1], mult * self.notional, self.currency, is_notional=True))

        return cfs
