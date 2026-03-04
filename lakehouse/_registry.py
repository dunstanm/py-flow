"""
Lakehouse alias registry — maps alias names to lakehouse connection info.
"""

from __future__ import annotations

import threading

_aliases: dict[str, dict] = {}
_lock = threading.Lock()


def register_alias(name: str, catalog_url: str, s3_endpoint: str,
                   s3_access_key: str = "minioadmin", s3_secret_key: str = "minioadmin",
                   s3_region: str = "us-east-1", warehouse: str = "lakehouse",
                   namespace: str = "default",
                   flight_host: str | None = None,
                   flight_port: int | None = None) -> None:
    """Register a lakehouse server alias.

    Args:
        flight_host: Optional RLS Flight SQL server hostname.
        flight_port: Optional RLS Flight SQL server port.
    """
    with _lock:
        _aliases[name] = {
            "catalog_url": catalog_url,
            "s3_endpoint": s3_endpoint,
            "s3_access_key": s3_access_key,
            "s3_secret_key": s3_secret_key,
            "s3_region": s3_region,
            "warehouse": warehouse,
            "namespace": namespace,
            "flight_host": flight_host,
            "flight_port": flight_port,
        }


def resolve_alias(name: str) -> dict | None:
    """Resolve a lakehouse alias to connection info."""
    with _lock:
        return _aliases.get(name)
