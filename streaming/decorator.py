"""
streaming.decorator — @ticking class decorator.

Annotates a Storable dataclass for *optional* streaming to a TickingTable.

**Default mode (compute library):**
  - @ticking is a pure metadata annotation — no tables, no connections.
  - .tick() is a no-op.
  - Zero Deephaven dependencies required.

**Streaming mode (activated explicitly):**
  - Call ``streaming.activate()`` to materialise TickingTable + LiveTable
    for all decorated classes.
  - .tick() then writes column values to the streaming engine.

Usage::

    @ticking
    @dataclass
    class FXSpot(Storable):
        __key__ = "pair"
        pair: str = ""
        bid: float = 0.0
        ...

    @ticking(exclude={"base_rate", "sensitivity"})
    @dataclass
    class YieldCurvePoint(Storable):
        __key__ = "label"
        ...

Adds to the class:
    cls._ticking_table   TickingTable instance (None until activated)
    cls._ticking_live    LiveTable (None until activated)
    cls._ticking_cols    [(col_name, attr_name, python_type), ...]
    cls._ticking_name    snake_case name derived from class name
    self.tick()          instance method — no-op unless streaming is active
"""

import re
from typing import Any

# Global registry: table_name → registration dict
# Tables/live views are None until streaming.activate() is called.
_registry: dict[str, dict] = {}

# Module-level flag: is streaming active?
_streaming_active = False

# Primitive types that map to ticking table columns
import datetime
_PRIMITIVE_TYPES = {str, float, int, bool, datetime.date, datetime.datetime}


def _to_snake_case(name: str) -> str:
    """Convert CamelCase class name to snake_case table name.

    FXSpot           → fx_spot
    YieldCurvePoint  → yield_curve_point
    IRSwapFixedFloatApprox → interest_rate_swap
    SwapPortfolio    → swap_portfolio
    """
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _resolve_column_specs(cls: type, exclude: set | None = None) -> list[tuple[str, str, type]]:
    """Pure-Python column resolution — no DH imports needed.

    Returns list of (col_name, attr_name, python_type).
    Skips non-primitive fields (object, list, etc.) and anything in exclude.
    """
    from reactive.computed import ComputedProperty

    exclude = set(exclude) if exclude else set()
    specs = []

    # 1. Dataclass fields (in definition order)
    for fname, fobj in cls.__dataclass_fields__.items():  # type: ignore[attr-defined]
        if fname in exclude or fname.startswith("_"):
            continue
        py_type = fobj.type
        if isinstance(py_type, str):
            py_type = {
                "str": str, "float": float, "int": int, "bool": bool,
                "date": datetime.date, "datetime": datetime.datetime
            }.get(py_type)
        if py_type not in _PRIMITIVE_TYPES:
            continue  # skip object, list, etc.
        specs.append((fname, fname, py_type))

    # 2. @computed properties (sorted for deterministic order)
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
        
        # Handle "from __future__ import annotations" stringified types
        if isinstance(ret, str):
            ret = {
                "str": str, "float": float, "int": int, "bool": bool,
                "date": datetime.date, "datetime": datetime.datetime
            }.get(ret)

        if ret not in _PRIMITIVE_TYPES:
            # Skip non-primitive return types (list, dict, object) 
            # instead of defaulting to float.
            continue
            
        specs.append((name, name, ret))

    return specs


def _tick_noop(self: Any) -> None:
    """No-op tick — streaming not active. This is the default."""
    pass


def _tick_live(self: Any) -> None:
    """Write all column values to the ticking table (streaming mode)."""
    cls = type(self)
    table = cls._ticking_table
    if table is None:
        return
    entry = _registry.get(cls._ticking_name)
    try:
        table.write_row(*(getattr(self, attr) for _, attr, _ in cls._ticking_cols))
        if entry is not None:
            entry["write_count"][0] += 1
    except RuntimeError as e:
        if "Deephaven session not available" in str(e):
            pass  # Silent fallback if DH went away
        else:
            raise


def _apply_ticking(cls: type, exclude: set | None = None) -> type:
    """Core logic: record metadata, attach no-op tick. Tables created later."""
    # Require __key__
    key = getattr(cls, "__key__", None)
    if key is None:
        raise ValueError(
            f"@ticking on {cls.__name__} requires a __key__ class variable "
            f"(e.g. __key__ = 'symbol')"
        )

    # Resolve columns (pure Python types — no DH imports)
    col_specs = _resolve_column_specs(cls, exclude)
    if not col_specs:
        raise ValueError(f"@ticking on {cls.__name__}: no columns resolved")

    # Table name from class name
    table_name = _to_snake_case(cls.__name__)

    # Attach metadata — no tables, no connections
    cls._ticking_table = None       # type: ignore[attr-defined]
    cls._ticking_live = None        # type: ignore[attr-defined]
    cls._ticking_cols = col_specs   # type: ignore[attr-defined]
    cls._ticking_name = table_name  # type: ignore[attr-defined]
    cls.tick = _tick_noop            # type: ignore[attr-defined]

    # Register for deferred materialisation
    _registry[table_name] = {
        "schema": {col_name: py_type for col_name, _, py_type in col_specs},
        "key": key,
        "cls": cls,
        "exclude": exclude,
        "table": None,
        "live": None,
        "write_count": [0],
    }

    return cls


def ticking(cls: type | None = None, *, exclude: set | None = None) -> type:
    """Class decorator: annotate a Storable for optional streaming.

    In default (compute) mode, this is pure metadata — no tables, no
    connections, no overhead.  Call ``streaming.activate()`` to create
    the underlying ticking tables when streaming is needed.

    Supports both bare and parameterized usage::

        @ticking                          # auto-infer all columns
        @ticking(exclude={"internal"})    # skip specific fields
    """
    if cls is not None:
        # Bare @ticking (no parentheses)
        return _apply_ticking(cls)
    # Parameterized @ticking(exclude=...)
    def decorator(cls: type) -> type:
        return _apply_ticking(cls, exclude=exclude)
    return decorator  # type: ignore[return-value]


# ===========================================================================
# Streaming activation (opt-in)
# ===========================================================================

def activate() -> None:
    """Materialise TickingTable + LiveTable for all @ticking-decorated classes.

    Call this *after* starting a StreamingServer.  Until this is called,
    all @ticking classes run in compute-only mode with no-op .tick().

    Example::

        from streaming.admin import StreamingServer
        from streaming.decorator import activate

        server = StreamingServer(port=10000).start()
        activate()   # tables created, .tick() becomes live
    """
    global _streaming_active
    from streaming.table import TickingTable

    for name, entry in _registry.items():
        if entry["table"] is not None:
            continue  # already materialised

        schema = entry["schema"]
        key = entry["key"]
        cls = entry["cls"]

        tt = TickingTable(schema)
        live = tt.last_by(key)

        entry["table"] = tt
        entry["live"] = live

        # Swap class-level pointers
        cls._ticking_table = tt
        cls._ticking_live = live
        cls.tick = _tick_live

    _streaming_active = True


# ===========================================================================
# Table accessors (for dashboard / streaming infrastructure)
# ===========================================================================

def get_tables() -> dict:
    """Return dict of all materialised tables: {name_raw: table, name_live: live}.

    Returns only tables that have been activated.  In compute-only mode,
    returns an empty dict.
    """
    tables = {}
    for name, entry in _registry.items():
        tt = entry["table"]
        live = entry["live"]
        if tt is not None:
            tables[f"{name}_raw"] = tt
        if live is not None:
            tables[f"{name}_live"] = live
    return tables


def get_active_tables() -> dict:
    """Return only materialised tables that have had at least one row written.

    Use instead of ``get_tables()`` when publishing to Deephaven::

        tables = get_active_tables()
        for name, tbl in tables.items():
            tbl.publish(name)
    """
    tables = {}
    for name, entry in _registry.items():
        tt = entry["table"]
        live = entry["live"]
        if tt is not None and entry["write_count"][0] > 0:
            tables[f"{name}_raw"] = tt
            if live is not None:
                tables[f"{name}_live"] = live
    return tables


def get_ticking_tables() -> dict:
    """Return dict of materialised TickingTable instances: {name: TickingTable}."""
    return {name: entry["table"] for name, entry in _registry.items() if entry["table"] is not None}


def clear_stale_tables(extra_names: list[str] | None = None) -> list[str]:
    """Remove from the Deephaven session any registered tables not written this run.

    When a Deephaven server persists between demo restarts (e.g. a Docker
    container left running), table names from the previous session remain
    bound in the query scope.  This function actively unbinds those names
    so the panel list reflects only the current run's active tables.

    Parameters
    ----------
    extra_names:
        Additional table name stems to clear (without ``_raw``/``_live`` suffix).
        Useful for clearing hand-crafted aggregates like ``swap_summary``.

    Returns
    -------
    list[str]
        The names that were successfully unbound.
    """
    from streaming.admin import _needs_docker
    _REMOTE = _needs_docker()

    cleared: list[str] = []

    # Collect all registered table names (raw + live variants) that are INACTIVE
    stale: list[str] = []
    for name, entry in _registry.items():
        if entry["write_count"][0] == 0:
            stale.append(f"{name}_raw")
            stale.append(f"{name}_live")

    # Add any caller-supplied extras
    for stem in (extra_names or []):
        stale.append(stem)

    if not stale:
        return cleared

    if _REMOTE:
        from streaming.table import _get_session
        session = _get_session()
        if session is None:
            return cleared
        for name in stale:
            try:
                session.run_script(f"if '{name}' in globals(): del {name}")
                cleared.append(name)
            except Exception:
                pass  # variable may not exist — safe to ignore
    else:
        # Local JVM (x86 embedded Deephaven)
        try:
            from deephaven.execution_context import get_exec_ctx
            scope = get_exec_ctx().j_exec_ctx.getQueryScope()
            for name in stale:
                try:
                    scope.removeParam(name)
                    cleared.append(name)
                except Exception:
                    pass
        except Exception:
            pass

    return cleared
