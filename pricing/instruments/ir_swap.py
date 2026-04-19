import datetime
from store.base import Storable
from reactive.traceable import traceable
from reactive.expr import Sum

class IRSwapBase:
    """
    Abstract Base Class for all explicit script-based Interest Rate Swaps.
    Subclasses must implement:
      - `leg_pay` and `leg_rec` mapping to logic like IRFixedLeg/IROISLeg
      - `discount_factor(currency, date)` to map currencies to dual-curves / FX matrices
    """
    
    @property
    def leg_pay(self):
        """Returns the fully constructed physical payment IRLeg."""
        raise NotImplementedError
        
    @property
    def leg_rec(self):
        """Returns the fully constructed physical receiving IRLeg."""
        raise NotImplementedError

    def discount_factor(self, currency: str, date: datetime.date):
        """Map localized cashflow currencies into base currency discount factors natively."""
        raise NotImplementedError

    def cashflows(self):
        """Generate identical full sequence schedule."""
        return self.leg_pay.cashflows() + self.leg_rec.cashflows()

    @traceable
    def npv(self) -> float:
        """Centralized Algebraic Evaluation engine integrating across generic explicit nodes."""
        cfs = self.cashflows()
        if not cfs:
            return 0.0
            
        pvs = []
        for cf in cfs:
            df = self.discount_factor(cf.currency, cf.date)
            if df is not None:
                from reactive.traced import TracedFloat
                pv = cf.amount * df
                pvs.append(pv)
        
        sum_expr = Sum(pvs)
        # sum(float(pv) for pv in pvs) avoids triggering AST evaluation without ambient context
        numeric_val = sum(float(pv) for pv in pvs)
        return TracedFloat(numeric_val, sum_expr) if pvs else 0.0



