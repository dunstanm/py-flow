# Streaming Module

Real-time ticking table abstraction over Deephaven. All locking, type mapping, and JVM interaction is hidden — user code works with Python types and never imports `deephaven` directly.

---

## Quick Start

```python
from streaming import TickingTable, flush, agg

# Create a writable ticking table with Python types
prices = TickingTable({
    "Symbol": str,
    "Price":  float,
    "Volume": int,
})

# Write rows (thread-safe)
prices.write_row("AAPL", 228.50, 1200)
prices.write_row("GOOGL", 171.30, 800)
flush()  # make pending writes visible

# Derive auto-locked views
prices_live = prices.last_by("Symbol")
top_movers  = prices_live.sort_descending("Price")

# Publish to Deephaven query scope (visible to all clients)
prices.publish("prices_raw")
prices_live.publish("prices_live")

# Snapshot to pandas
df = prices_live.snapshot()
```

---

## Architecture

```
User Code                    streaming module              Deephaven JVM
─────────                    ────────────────              ─────────────
TickingTable(schema)    →    DynamicTableWriter            JVM table
  .write_row(...)       →      .write_row(...)             append row
  .last_by("Key")       →    shared_lock(UG) + lastBy()   derived table
  .agg_by([...])        →    shared_lock(UG) + aggBy()    derived table
  .snapshot()           →    shared_lock(UG) + to_pandas   DataFrame
  .publish("name")      →    queryScope.putParam()         global scope
flush()                 →    UG.requestRefresh()            cycle graph
```

All derivation operations (`last_by`, `agg_by`, `sort_descending`, `where`, `select`, `update`) acquire the update graph shared lock automatically. Users never lock manually.

---

## Core Classes

### `TickingTable`

Writable ticking table backed by a `DynamicTableWriter`. Inherits all `LiveTable` operations.

```python
from streaming import TickingTable

prices = TickingTable({
    "Symbol":    str,
    "Price":     float,
    "Bid":       float,
    "Ask":       float,
    "Volume":    int,
    "Change":    float,
    "ChangePct": float,
})
```

**Supported Python types:**

| Python Type | Deephaven Type |
|-------------|----------------|
| `str`       | `string`       |
| `int`       | `int64`        |
| `float`     | `double`       |
| `bool`      | `bool_`        |
| `datetime`  | `Instant`      |
| `Decimal`   | `double`       |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `.write_row(*values)` | — | Write a single row. Thread-safe. |
| `.flush()` | — | Flush the update graph (alias for module-level `flush()`). |
| `.close()` | — | Close the underlying writer. |

Plus all `LiveTable` methods below.

### `LiveTable`

Read-only derived table. All operations auto-acquire the UG shared lock.

| Method | Returns | Description |
|--------|---------|-------------|
| `.last_by(by)` | `LiveTable` | Latest row per group key. |
| `.agg_by(aggs, by_columns=None)` | `LiveTable` | Aggregation (sum, avg, count, etc). |
| `.sort_descending(by)` | `LiveTable` | Sort descending by column(s). |
| `.where(filters)` | `LiveTable` | Filter rows. |
| `.select(columns)` | `LiveTable` | Select/rename columns. |
| `.update(formulas)` | `LiveTable` | Add computed columns. |
| `.snapshot()` | `DataFrame` | Pandas snapshot of current state. |
| `.publish(name)` | — | Publish to DH query scope (visible to all clients). |
| `.size` | `int` | Current row count. |

---

## Aggregations

```python
from streaming import agg

summary = prices_live.agg_by([
    agg.sum(["TotalVolume=Volume"]),
    agg.avg(["AvgPrice=Price"]),
    agg.count("NumSymbols"),
    agg.min(["MinPrice=Price"]),
    agg.max(["MaxPrice=Price"]),
    agg.first(["FirstSymbol=Symbol"]),
    agg.last(["LastSymbol=Symbol"]),
    agg.std(["StdPrice=Price"]),
    agg.var(["VarPrice=Price"]),
    agg.median(["MedPrice=Price"]),
    agg.pct(0.95, ["P95Price=Price"]),
    agg.weighted_avg("Volume", ["WAvgPrice=Price"]),
])
```

All aggregation functions are lazy-imported to avoid JVM initialization at import time.

---

## `@ticking` Decorator

Auto-creates a `TickingTable` + `LiveTable` from a `Storable` dataclass:

```python
from streaming import ticking, get_tables, flush
from store.base import Storable
from dataclasses import dataclass

@ticking
@dataclass
class FXSpot(Storable):
    pair: str = ""
    bid: float = 0.0
    ask: float = 0.0

# Write via .tick()
spot = FXSpot(pair="EUR/USD", bid=1.0850, ask=1.0852)
spot.tick()
flush()

# Access the underlying tables
FXSpot._ticking      # TickingTable (raw, append-only)
FXSpot._ticking_live # LiveTable (last_by entity key)

# Publish all decorated tables
tables = get_tables()
for name, tbl in tables.items():
    tbl.publish(name)
```

---

## `flush()`

Flushes the Deephaven update graph so pending writes become visible to derived tables.

```python
from streaming import flush

prices.write_row("AAPL", 230.0, 1500)
flush()  # derived tables now see the new row
```

**Thread-safe:** The update graph reference is cached on the first call, so `flush()` works from any thread (background writers, async consumers, etc).

---

## Bridge Integration

The `StoreBridge` uses `TickingTable` internally — store events stream into ticking tables with no manual DH imports:

```python
from bridge import StoreBridge

bridge = StoreBridge(host=host, port=port, dbname=dbname,
                     user="bridge_user", password="bridge_pw")
bridge.register(Order)
bridge.start()

# Returns a TickingTable — all derivations auto-locked
orders = bridge.table(Order)
orders_live = orders.last_by("EntityId")
orders_live.publish("orders_live")
```

---

## Publishing Tables

`.publish(name)` puts the table into Deephaven's query scope, making it visible to all connected clients:

```python
prices.publish("prices_raw")
prices_live.publish("prices_live")
```

Clients see these via `DeephavenClient`:

```python
from base_client import DeephavenClient

with DeephavenClient() as c:
    tables = c.list_tables()        # includes "prices_raw", "prices_live"
    df = c.open_table("prices_live").to_arrow().to_pandas()
```

---

## JVM Signal Handling

The Deephaven JVM uses `SIGSEGV` internally for safepoint polling. Python's `faulthandler` (enabled by default in pytest) intercepts this signal and aborts the process.

**Fix:** Disable faulthandler in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
faulthandler_timeout = 0
addopts = "-p no:faulthandler"
```

This is required for any test suite that runs with an embedded Deephaven JVM.

---

## Full Example: Trading Server

```python
from streaming import TickingTable, agg, flush

# Schema
prices = TickingTable({
    "Symbol": str, "Price": float, "Bid": float,
    "Ask": float, "Volume": int, "Change": float, "ChangePct": float,
})

risk = TickingTable({
    "Symbol": str, "Price": float, "Position": int,
    "MarketValue": float, "UnrealizedPnL": float,
    "Delta": float, "Gamma": float, "Theta": float, "Vega": float,
})

# Derived tables (auto-locked)
prices_live = prices.last_by("Symbol")
risk_live   = risk.last_by("Symbol")

portfolio = risk_live.agg_by([
    agg.sum(["TotalMV=MarketValue", "TotalPnL=UnrealizedPnL"]),
    agg.avg(["AvgGamma=Gamma", "AvgTheta=Theta"]),
    agg.count("NumPositions"),
])

top_movers      = prices_live.sort_descending("ChangePct")
volume_leaders  = prices_live.sort_descending("Volume")

# Publish all
prices.publish("prices_raw")
prices_live.publish("prices_live")
risk.publish("risk_raw")
risk_live.publish("risk_live")
portfolio.publish("portfolio_summary")
top_movers.publish("top_movers")
volume_leaders.publish("volume_leaders")

# Feed ticks from any source
def on_tick(tick):
    prices.write_row(tick["symbol"], tick["price"], ...)
    flush()
```
