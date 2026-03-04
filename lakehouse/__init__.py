"""
Lakehouse — Iceberg Analytical Store
======================================
Read, ingest, and transform data in Apache Iceberg tables.

User API::

    from lakehouse import Lakehouse

    lh = Lakehouse()
    lh.query("SELECT * FROM lakehouse.default.events LIMIT 10")
    lh.ingest("my_signals", df, mode="snapshot")
    lh.transform("daily_pnl", "SELECT ... GROUP BY ...", mode="incremental", primary_key="id")
    lh.close()

Row-Level Security (just add ``token=``)::

    lh = Lakehouse("demo", token="alice-token")
    lh.query("SELECT * FROM lakehouse.default.sales_data")  # → RLS-filtered

Platform/admin APIs live in ``lakehouse.admin``.
"""

from lakehouse.query import Lakehouse, LakehouseQuery

__all__ = [
    "Lakehouse",
    "LakehouseQuery",  # deprecated alias
]
