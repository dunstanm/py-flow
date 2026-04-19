from __future__ import annotations
import datetime
from dataclasses import dataclass
from typing import Union, Any

# We use Any/Union typing to allow plain float, DualExpr, or streaming/SQL AST objects
ExprT = Any  

@dataclass
class CashFlow:
    """
    Representation of an explicit algebraic CashFlow. 
    
    This replaces hardcoded closed-form `npv` accumulators by emitting transparent,
    inspectable collections of algebraic expressions. This enables advanced XVA netting 
    sets, delayed counterparty risk scoring, and general scripting logic.
    """
    date: datetime.date
    amount: ExprT
    currency: str
    is_notional: bool = False
