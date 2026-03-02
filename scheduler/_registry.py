"""Scheduler alias registry (internal)."""

import threading

_aliases: dict[str, dict] = {}
_lock = threading.Lock()


def register_alias(name: str, server):
    """Register a scheduler server under an alias name."""
    with _lock:
        _aliases[name] = {"server": server}


def resolve_alias(name: str) -> dict | None:
    """Resolve an alias to its server reference."""
    with _lock:
        return _aliases.get(name)
