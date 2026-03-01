"""
store.dh — Backward-compatibility shim.

This module re-exports from ``streaming.decorator`` which now owns the
``@ticking`` (formerly ``@dh_table``) decorator.

Prefer importing directly from ``streaming``::

    from streaming import ticking, get_tables
"""

# Re-export everything callers may need
from streaming.decorator import (
    ticking as dh_table,
    get_tables as get_dh_tables,
    _to_snake_case,
    _resolve_column_specs,
)
