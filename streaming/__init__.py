"""
streaming — Optional Real-Time Ticking Table Layer
====================================================
Annotates domain classes for *optional* streaming to a ticking engine
(currently Deephaven).

**Default mode (compute library):**
  - ``@ticking`` is a pure metadata annotation — zero overhead.
  - ``.tick()`` is a no-op.
  - No Deephaven connection or JVM required.

**Streaming mode (opt-in):**
  - Start a ``StreamingServer``, then call ``streaming.activate()``.
  - ``.tick()`` writes column values to live ticking tables.

Public surface::

    from streaming import ticking              # decorator
    from streaming import activate             # opt-in streaming
    from streaming import get_tables           # table accessors

Platform lifecycle lives in ``streaming.admin``.
"""

from streaming.decorator import (
    activate,
    clear_stale_tables,
    get_active_tables,
    get_tables,
    get_ticking_tables,
    ticking,
)

__all__ = [
    "activate",
    "clear_stale_tables",
    "get_active_tables",
    "get_tables",
    "get_ticking_tables",
    "ticking",
]


# Lazy accessors — only import heavy modules when actually needed
def __getattr__(name: str):
    """Lazy import for streaming infrastructure that needs Deephaven."""
    if name in ("LiveTable", "TickingTable", "flush", "snapshot"):
        from streaming import table
        return getattr(table, name)
    if name == "agg":
        from streaming import agg as _agg
        return _agg
    if name == "StreamingClient":
        from streaming.client import StreamingClient
        return StreamingClient
    if name in ("PortInUseError", "assert_ports_free", "check_ports",
                "preflight_check", "probe_ports"):
        from streaming import port_check
        return getattr(port_check, name)
    raise AttributeError(f"module 'streaming' has no attribute {name!r}")
