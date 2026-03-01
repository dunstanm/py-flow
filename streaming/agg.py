"""
streaming.agg — Aggregation helpers re-exported from Deephaven.

Usage::

    from streaming import agg

    summary = live.agg_by([
        agg.sum(["TotalMV=MarketValue"]),
        agg.avg(["AvgGamma=Gamma"]),
        agg.count("NumPositions"),
    ])

All functions are thin wrappers that defer the ``deephaven`` import
until first call (the JVM must be running).
"""

from __future__ import annotations


def _dh_agg():
    from deephaven import agg as _agg
    return _agg


# -- primary aggregations used in the codebase ----------------------------

def sum(cols):
    """Sum columns.  Wraps ``deephaven.agg.sum_``."""
    return _dh_agg().sum_(cols)


def avg(cols):
    """Average columns.  Wraps ``deephaven.agg.avg``."""
    return _dh_agg().avg(cols)


def count(col: str):
    """Count rows.  Wraps ``deephaven.agg.count_``."""
    return _dh_agg().count_(col)


def min(cols):
    """Min columns.  Wraps ``deephaven.agg.min_``."""
    return _dh_agg().min_(cols)


def max(cols):
    """Max columns.  Wraps ``deephaven.agg.max_``."""
    return _dh_agg().max_(cols)


def first(cols):
    """First value per group.  Wraps ``deephaven.agg.first``."""
    return _dh_agg().first(cols)


def last(cols):
    """Last value per group.  Wraps ``deephaven.agg.last``."""
    return _dh_agg().last(cols)


def std(cols):
    """Standard deviation.  Wraps ``deephaven.agg.std``."""
    return _dh_agg().std(cols)


def var(cols):
    """Variance.  Wraps ``deephaven.agg.var``."""
    return _dh_agg().var(cols)


def median(cols):
    """Median.  Wraps ``deephaven.agg.median``."""
    return _dh_agg().median(cols)
