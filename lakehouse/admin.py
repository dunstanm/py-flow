"""
Lakehouse Admin — Platform & Infrastructure APIs
==================================================
Start/stop the lakehouse stack, run sync services, manage catalogs and tables.

These are NOT user-facing APIs. Users should only import from ``lakehouse``
(which exposes ``Lakehouse``).

Platform usage::

    from lakehouse.admin import start_lakehouse, stop_lakehouse, SyncEngine

    stack = await start_lakehouse()
    catalog = create_catalog(uri=stack.catalog_url, s3_endpoint=stack.s3_endpoint)
    ensure_tables(catalog)

    sync = SyncEngine(catalog=catalog)
    sync.sync_events(pg_conn)
    sync.sync_ticks(backend)

    await stop_lakehouse(stack)
"""

from lakehouse.services import start_lakehouse, stop_lakehouse, LakehouseStack
from lakehouse.sync import SyncEngine
from lakehouse.models import SyncState
from lakehouse.catalog import create_catalog
from lakehouse.tables import ensure_tables

__all__ = [
    # Lifecycle
    "start_lakehouse",
    "stop_lakehouse",
    "LakehouseStack",
    # Sync service
    "SyncEngine",
    "SyncState",
    # Bootstrap
    "create_catalog",
    "ensure_tables",
]
