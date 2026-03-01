"""
streaming — Real-Time Ticking Table Server
============================================
Wraps the streaming engine (currently Deephaven) behind a consistent API.

Public surface::

    from streaming import TickingTable, LiveTable, flush
    from streaming import agg
    from streaming import ticking, get_tables

Platform lifecycle lives in ``streaming.admin``.
"""

from streaming.table import TickingTable, LiveTable, flush
from streaming.decorator import ticking, get_tables, get_ticking_tables
from streaming.client import StreamingClient
from streaming import agg

__all__ = [
    "TickingTable",
    "LiveTable",
    "flush",
    "ticking",
    "get_tables",
    "get_ticking_tables",
    "StreamingClient",
    "agg",
]
