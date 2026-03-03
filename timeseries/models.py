"""
Time-Series Models
==================
Backend-agnostic Pydantic models for historical market data queries and results.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Bar(BaseModel):
    """OHLCV bar aggregated from raw ticks."""

    symbol: str
    interval: str           # "1m", "5m", "15m", "1h", "4h", "1d"
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None  # None for FX/curve bars
    trade_count: int
    timestamp: datetime


class HistoryQuery(BaseModel):
    """Query parameters for raw tick history."""

    type: str               # "equity", "fx", "curve"
    symbol: str
    start: datetime | None = None
    end: datetime | None = None
    limit: int = 1000


class BarQuery(BaseModel):
    """Query parameters for OHLCV bar aggregation."""

    type: str               # "equity", "fx", "curve"
    symbol: str
    interval: str = "1m"    # "1m", "5m", "15m", "1h", "4h", "1d"
    start: datetime | None = None
    end: datetime | None = None
