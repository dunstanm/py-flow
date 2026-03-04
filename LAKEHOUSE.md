# Lakehouse — Iceberg Analytical Store

All reads and writes via DuckDB SQL (Iceberg extension + REST catalog). Lakekeeper REST catalog + S3-compatible storage. Syncs platform data from PG and QuestDB, plus user-facing ingest/transform API. Optional **Row-Level Security** via Arrow Flight SQL gateway.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Platform Sync (SyncEngine)     User API (Lakehouse)            │
│                                                                 │
│  PG object_events ──→ PyIceberg ──→ S3 storage                │
│  QuestDB ticks    ──→            ──→ (Parquet)                  │
│                                                                 │
│  Lakehouse.ingest()  ──→ DuckDB SQL ──→ Iceberg ──→ S3        │
│  Lakehouse.transform() ──→                                      │
│  Lakehouse.query()   ──→ DuckDB SQL ──→ reads Parquet           │
│                                                                 │
│  Lakekeeper REST Catalog ──→ PG (catalog metadata)              │
│                                                                 │
│  ┌─ Lakehouse("demo", token="alice") ─────────────────────┐    │
│  │  Open tables    → direct DuckDB (zero overhead)         │    │
│  │  Protected tables → Flight SQL → RLS rewrite → DuckDB  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

| Component | Technology | Port |
|-----------|-----------|------|
| **Catalog** | Lakekeeper (Rust binary) | 8181 |
| **Storage** | S3-compatible (via objectstore) | 9002 (API), 9003 (Console) |
| **Read/Write** | DuckDB 1.4 + Iceberg extension | In-process |
| **Platform Sync** | PyIceberg + PyArrow | In-process |
| **RLS Gateway** | Arrow Flight SQL (gRPC) | Auto-assigned |

---

## Quick Start

```bash
pip install -e ".[lakehouse]"
python3 demo_lakehouse.py   # auto-starts object store + Lakekeeper
python3 demo_lakehouse_rls.py   # RLS demo: two users, row-level isolation
```

```python
from lakehouse import Lakehouse

lh = Lakehouse()

# Query
lh.query("SELECT * FROM lakehouse.default.events LIMIT 10")

# Ingest
lh.ingest("my_signals", df, mode="append")

# Transform
lh.transform("daily_pnl", "SELECT ... GROUP BY ...", mode="snapshot")

lh.close()
```

---

## Package Layout

```
lakehouse/
├── __init__.py      # Public API: Lakehouse
├── query.py         # Lakehouse class: query, ingest, transform, hybrid RLS routing
├── rls_server.py    # RLSFlightServer, RLSPolicy, RLSRewriter, TokenServerAuthHandler
├── admin.py         # LakehouseServer (manages stack + RLS lifecycle), RLSPolicy export
├── catalog.py       # PyIceberg REST catalog setup via Lakekeeper
├── tables.py        # Iceberg table definitions (events, ticks, bars_daily, positions)
├── sync.py          # Incremental ETL: PG + QuestDB → Iceberg (watermark-based)
├── services.py      # Lakekeeper binary lifecycle + objectstore integration
├── _registry.py     # Internal alias registry (flight_host/flight_port)
└── models.py        # Pydantic: SyncState, TableInfo
```

---

## Write Modes

All write modes automatically add `_batch_id` (UUID) and `_batch_ts` (timestamp) to every row. Each `ingest()` or `transform()` call gets a unique batch ID.

### `append`

Raw append. Every row gets `_batch_id` and `_batch_ts`.

```python
lh.ingest("raw_signals", data, mode="append")
```

| Metadata column | Description |
|-----------------|-------------|
| `_batch_id` | UUID identifying this ingest call |
| `_batch_ts` | Timestamp of this ingest call |

### `snapshot`

Batch-level versioning. Previous batch rows are set to `_is_current = false`.

```python
lh.ingest("daily_snapshot", data, mode="snapshot")

# Query current snapshot
lh.query("SELECT * FROM lakehouse.default.daily_snapshot WHERE _is_current = true")

# Query a specific historical batch
lh.query("SELECT * FROM lakehouse.default.daily_snapshot WHERE _batch_id = '...'")
```

| Metadata column | Description |
|-----------------|-------------|
| `_batch_id` | UUID identifying this ingest call |
| `_batch_ts` | Timestamp of this ingest call |
| `_is_current` | `true` for latest batch, `false` for expired |

### `incremental`

Row-level upsert by primary key. Matching rows are soft-expired (`_is_current = false`), new versions inserted. Requires `primary_key`.

```python
lh.ingest("trades", data, mode="incremental", primary_key="trade_id")

# Current state
lh.query("SELECT * FROM lakehouse.default.trades WHERE _is_current = true")

# Full history for a specific trade
lh.query("SELECT * FROM lakehouse.default.trades WHERE trade_id = 'T1' ORDER BY _updated_at")
```

| Metadata column | Description |
|-----------------|-------------|
| `_batch_id` | UUID identifying this ingest call |
| `_batch_ts` | Timestamp of this ingest call |
| `_is_current` | `true` for latest version, `false` for expired |
| `_updated_at` | When this row was written or expired |

### `bitemporal`

System time + business time versioning. Like incremental, plus `_tx_time`, `_valid_from`, `_valid_to` for full temporal queries. Requires `primary_key`.

```python
lh.ingest("positions", data, mode="bitemporal", primary_key="entity_id")

# Current state
lh.query("SELECT * FROM lakehouse.default.positions WHERE _is_current = true")

# What was effective at a specific time?
lh.query("""
    SELECT * FROM lakehouse.default.positions
    WHERE _valid_from <= '2026-01-15' AND (_valid_to IS NULL OR _valid_to > '2026-01-15')
""")
```

| Metadata column | Description |
|-----------------|-------------|
| `_batch_id` | UUID identifying this ingest call |
| `_batch_ts` | Timestamp of this ingest call |
| `_is_current` | `true` for latest version, `false` for expired |
| `_tx_time` | System time — when this row was recorded/expired |
| `_valid_from` | Business time — when this fact becomes effective |
| `_valid_to` | Business time — when this fact expires (`NULL` = open) |

Users may supply `_valid_from` and `_valid_to` in their data; if absent, defaults to `now()` and `NULL`.

---

## Metadata Summary

| Column | append | snapshot | incremental | bitemporal |
|--------|--------|----------|-------------|------------|
| `_batch_id` | ✅ | ✅ | ✅ | ✅ |
| `_batch_ts` | ✅ | ✅ | ✅ | ✅ |
| `_is_current` | — | ✅ | ✅ | ✅ |
| `_updated_at` | — | — | ✅ | — |
| `_tx_time` | — | — | — | ✅ |
| `_valid_from` | — | — | — | ✅ |
| `_valid_to` | — | — | — | ✅ |

---

## Query Interface

Direct DuckDB SQL via Python — no REST API:

```python
from lakehouse import Lakehouse

lh = Lakehouse()

# List of dicts
lh.query("SELECT type_name, count(*) as cnt FROM lakehouse.default.events GROUP BY type_name")

# PyArrow Table
arrow_table = lh.query_arrow("SELECT * FROM lakehouse.default.events LIMIT 100")

# Pandas DataFrame
df = lh.query_df("SELECT * FROM lakehouse.default.ticks LIMIT 100")

# Cross-dataset join
lh.query("""
    SELECT e.type_name, e.entity_id, t.symbol, t.price
    FROM lakehouse.default.events e
    JOIN lakehouse.default.ticks t
      ON json_extract_string(e.data, '$.symbol') = t.symbol
    LIMIT 20
""")

lh.close()
```

### Transform

Run a SQL query and write results into an Iceberg table. Equivalent to `ingest(table, query_arrow(sql), mode, pk)`:

```python
# Materialized view with batch history
lh.transform("daily_summary",
    "SELECT type_name, count(*) as cnt FROM lakehouse.default.events GROUP BY type_name",
    mode="snapshot")

# Row-level upsert from SQL
lh.transform("latest_prices",
    "SELECT symbol, last(price) as price FROM lakehouse.default.ticks GROUP BY symbol",
    mode="incremental", primary_key="symbol")
```

---

## Row-Level Security (RLS)

Enforces row-level access control by routing protected-table queries through an Arrow Flight SQL gateway. The server rewrites SQL using `sqlglot` to inject ACL table joins. Open tables bypass Flight entirely — zero overhead.

### How it works

1. `LakehouseServer` starts an `RLSFlightServer` alongside PG/Lakekeeper/MinIO
2. The server publishes which tables are protected via a `get_protected_tables` action
3. `Lakehouse(token=)` fetches this set on init and caches it
4. For each query, `sqlglot` extracts table names → checks membership → routes accordingly
5. Protected queries go through Flight: server rewrites SQL with `INNER JOIN` to ACL table

### Platform setup

```python
from lakehouse.admin import LakehouseServer, RLSPolicy

server = LakehouseServer(
    rls_policies=[
        RLSPolicy(
            table_name="sales_data",     # the protected table
            acl_table="sales_acl",       # ACL mapping table
            join_column="row_id",        # shared key
            user_column="user_token",    # column with user identity
        ),
    ],
    rls_users={"alice-token": "alice", "bob-token": "bob"},
)
await server.start()            # starts PG + Lakekeeper + MinIO + Flight SQL
server.register_alias("demo")   # alias includes Flight endpoint automatically
```

### User code

```python
from lakehouse import Lakehouse

# Open tables → direct DuckDB (zero overhead)
# Protected tables → Flight SQL (RLS-filtered)
lh = Lakehouse("demo", token="alice-token")

lh.query("SELECT * FROM lakehouse.default.trades")       # open → all rows
lh.query("SELECT * FROM lakehouse.default.sales_data")   # protected → alice's rows only
```

### SQL Rewriting

The `RLSRewriter` transforms:

```sql
SELECT * FROM sales_data WHERE region = 'US'
```

Into:

```sql
SELECT sales_data.* FROM sales_data AS sales_data
INNER JOIN sales_acl AS _acl
  ON sales_data.row_id = _acl.row_id AND _acl.user_token = 'alice-token'
WHERE region = 'US'
```

### RLSPolicy fields

| Field | Description |
|-------|-------------|
| `table_name` | The protected table name |
| `acl_table` | ACL table with row-level grants |
| `join_column` | Column shared between data and ACL tables |
| `user_column` | Column in ACL table holding the user token |

---

## Platform Tables (SyncEngine)

| Table | Source | Partition | Description |
|-------|--------|-----------|-------------|
| `events` | PG `object_events` | `type_name`, `day(tx_time)` | Full bi-temporal audit trail |
| `ticks` | QuestDB tick tables | `tick_type`, `day(timestamp)` | Unified equity/fx/curve ticks |
| `bars_daily` | QuestDB OHLCV bars | `symbol`, `month(timestamp)` | Pre-aggregated daily bars |
| `positions` | PG (Position entities) | `day(valid_from)` | Position snapshots |

### Sync Engine

Incremental sync with watermarks — no full table scans after initial load:

```python
from lakehouse import create_catalog, ensure_tables, SyncEngine

catalog = create_catalog()
ensure_tables(catalog)
sync = SyncEngine(catalog=catalog)

# Sync from PG
sync.sync_events(pg_conn)

# Sync from QuestDB
sync.sync_ticks(questdb_reader)
sync.sync_bars(questdb_reader)

# Or sync everything at once
sync.sync_all(pg_conn=pg, questdb_reader=reader)

# Check state
print(sync.state)  # SyncState(events_watermark=..., events_synced=42, ...)
```

Watermarks persisted to `data/lakehouse/sync_state.json`.

---

## Service Management

Lakekeeper is auto-downloaded and subprocess-managed. Object storage uses the `objectstore` package:

```python
import asyncio
from lakehouse.services import start_lakehouse, stop_lakehouse

stack = asyncio.run(start_lakehouse(data_dir="data/lakehouse"))
# stack.catalog_url, stack.s3_endpoint, stack.pg_url

asyncio.run(stop_lakehouse(stack))
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LAKEKEEPER_URI` | `http://localhost:8181/catalog` | Lakekeeper REST catalog URL |
| `LAKEKEEPER_PG_URL` | (from pgserver) | PG connection URL for Lakekeeper |
| `LAKEHOUSE_WAREHOUSE` | `lakehouse` | Iceberg warehouse name |
| `S3_ENDPOINT` | `http://localhost:9002` | S3-compatible endpoint |
| `S3_ACCESS_KEY` | `minioadmin` | S3 access key |
| `S3_SECRET_KEY` | `minioadmin` | S3 secret key |

---

## Dependencies

```toml
[project.optional-dependencies]
lakehouse = [
    "pyiceberg[pyarrow]>=0.8.0",
    "duckdb>=1.4.0",
    "pyarrow>=14.0",
    "httpx>=0.27.0",
    "sqlglot>=26.0",
    "adbc-driver-flightsql>=1.0.0",
]
```

### Binary Dependencies (auto-downloaded on first run)

| Binary | Size | Language | Purpose |
|--------|------|----------|---------|
| Lakekeeper | ~30MB | Rust | Iceberg REST catalog |
| Object store | ~100MB | Go | S3-compatible storage (via objectstore) |

---

## Process Summary

| Process | Port | Language | Role |
|---------|------|----------|------|
| PostgreSQL (embedded) | 5488 | C | Object store + Lakekeeper catalog metadata |
| Lakekeeper | 8181 | Rust | Iceberg REST catalog API |
| Object store | 9002/9003 | Go | S3 storage for Parquet data files |
| RLS Flight SQL | Auto | Python | Arrow Flight gateway for row-level security |
| QuestDB | 8812/9000/9009 | Java | Time-series DB (optional, for tick sync) |
