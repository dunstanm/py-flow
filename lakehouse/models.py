"""
Lakehouse Models
=================
Pydantic models for sync state and table metadata.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SyncState(BaseModel):
    """Tracks watermarks for incremental sync."""
    events_watermark: datetime | None = None
    ticks_watermark: datetime | None = None
    bars_watermark: datetime | None = None
    last_sync_time: datetime | None = None
    events_synced: int = 0
    ticks_synced: int = 0
    bars_synced: int = 0


class TableInfo(BaseModel):
    """Metadata about an Iceberg table."""
    name: str
    namespace: str = "default"
    location: str = ""
    current_snapshot_id: int | None = None
    snapshot_count: int = 0
    schema_fields: list[str] = Field(default_factory=list)
    partition_fields: list[str] = Field(default_factory=list)
