"""
streaming.decorator — @ticking class decorator.

Auto-creates a TickingTable from a Storable dataclass, deriving column
schema from dataclass fields and @computed properties.
"""

import re
from typing import Any

from streaming.table import LiveTable, TickingTable

# Global registry: table_name -> {cls, schema, key}
_registry_config: dict[str, dict] = {}
# Runtime cache: table_name -> (TickingTable, LiveTable)
_registry_runtime: dict[str, tuple[TickingTable, LiveTable]] = {}

# Primitive types that map to ticking table columns
_PRIMITIVE_TYPES = {str, float, int, bool}


def _to_snake_case(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _resolve_column_specs(cls: type, exclude: set | None = None) -> list[tuple[str, str, type]]:
    from reactive.computed import ComputedProperty
    exclude = set(exclude) if exclude else set()
    specs = []

    for fname, fobj in cls.__dataclass_fields__.items():
        if fname in exclude or fname.startswith("_"):
            continue
        py_type = fobj.type
        if isinstance(py_type, str):
            py_type = {"str": str, "float": float, "int": int, "bool": bool}.get(py_type)
        if py_type not in _PRIMITIVE_TYPES:
            continue
        specs.append((fname, fname, py_type))

    computed_names = sorted(
        name
        for name in dir(cls)
        if not name.startswith("_")
        and name not in exclude
        and isinstance(getattr(cls, name, None), ComputedProperty)
    )
    for name in computed_names:
        cp = getattr(cls, name)
        ret = getattr(cp.fn, "__annotations__", {}).get("return", float)
        if isinstance(ret, str):
            ret = {"str": str, "float": float, "int": int, "bool": bool}.get(ret)
        if ret not in _PRIMITIVE_TYPES:
            ret = float
        specs.append((name, name, ret))
    return specs


def _get_or_create_tables(table_name: str) -> tuple[TickingTable, LiveTable]:
    """Lazy creation of TickingTable and LiveTable on demand."""
    if table_name in _registry_runtime:
        return _registry_runtime[table_name]
    
    config = _registry_config[table_name]
    schema = config["schema"]
    key = config["key"]
    
    tt = TickingTable(schema)
    live = tt.last_by(key)
    res = (tt, live)
    _registry_runtime[table_name] = res
    return res


class TickingTableDescriptor:
    """Descriptor to provide lazy access to _ticking_table."""
    def __get__(self, instance, owner):
        table_name = owner._ticking_name
        tt, _ = _get_or_create_tables(table_name)
        return tt

class LiveTableDescriptor:
    """Descriptor to provide lazy access to _ticking_live."""
    def __get__(self, instance, owner):
        table_name = owner._ticking_name
        _, live = _get_or_create_tables(table_name)
        return live


def _tick(self: Any) -> None:
    cls = type(self)
    values = [getattr(self, attr) for _, attr, _ in cls._ticking_cols]
    # Trigger lazy creation if needed
    cls._ticking_table.write_row(*values)


def _apply_ticking(cls: type, exclude: set | None = None) -> type:
    key = getattr(cls, "__key__", None)
    if key is None:
        raise ValueError(f"@ticking on {cls.__name__} requires a __key__")

    col_specs = _resolve_column_specs(cls, exclude)
    if not col_specs:
        raise ValueError(f"@ticking on {cls.__name__}: no columns resolved")

    table_name = _to_snake_case(cls.__name__)
    schema = {col_name: py_type for col_name, _, py_type in col_specs}

    # Register configuration for lazy creation
    _registry_config[table_name] = {"schema": schema, "key": key}

    # Attach descriptors and metadata
    cls._ticking_cols = col_specs
    cls._ticking_name = table_name
    cls._ticking_table = TickingTableDescriptor()
    cls._ticking_live = LiveTableDescriptor()
    cls.tick = _tick

    return cls


def ticking(cls: type | None = None, *, exclude: set | None = None) -> type:
    if cls is not None:
        return _apply_ticking(cls)
    def decorator(cls: type) -> type:
        return _apply_ticking(cls, exclude=exclude)
    return decorator


def get_tables() -> dict:
    """Trigger creation of all registered tables and return them."""
    tables = {}
    for name in _registry_config:
        tt, live = _get_or_create_tables(name)
        tables[f"{name}_raw"] = tt
        tables[f"{name}_live"] = live
    return tables


def get_ticking_tables() -> dict:
    return {name: _get_or_create_tables(name)[0] for name in _registry_config}
