# Scheduler — Cron-Based Task Execution

Schedule functions and multi-step pipelines with cron expressions, dependency graphs, parallel execution, and durable workflows. Everything is a task list — a single function is just a one-element list.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  @schedule("*/5 * * * *")              USER CODE                 │
│  def ingest(): ...                                               │
│                                                                  │
│  @schedule("0 2 * * *", name="etl")                              │
│  def extract(): ...                                              │
│                                                                  │
│  @schedule("0 2 * * *", name="etl", depends_on=["extract"])      │
│  def transform(): ...                                            │
│                                                                  │
│  scheduler = Scheduler("demo")         # alias-based             │
│  scheduler.register(Schedule(...))     # programmatic            │
│  scheduler.fire("etl")                 # manual trigger          │
│  scheduler.pause("etl")               # management              │
│  scheduler.history("etl")             # query runs               │
└────────────────────────────┬─────────────────────────────────────┘
                             │ alias
┌────────────────────────────▼─────────────────────────────────────┐
│                 SchedulerServer (self-contained)                  │
│                                                                  │
│  Embedded PG (StoreServer)                                       │
│  ├── Schedule Storable (cron + tasks)                            │
│  ├── Run Storable (execution record + task results)              │
│  └── State machines (ACTIVE/PAUSED, PENDING→RUNNING→SUCCESS)     │
│                                                                  │
│  WorkflowEngine (DBOS, same PG)                                  │
│  ├── Checkpointed steps (crash recovery)                         │
│  └── DAGRunner (parallel branches, skip on failure)              │
│                                                                  │
│  Tick loop (check cron, fire due schedules)                      │
│  resolve_fn (importlib: "module:qualname" → callable)            │
│  collect_schedules() ← flush @schedule to PG                     │
└──────────────────────────────────────────────────────────────────┘
```

| Component | Technology | Purpose |
|-----------|-----------|--------|
| **SchedulerServer** | Embedded PG + DBOS | Self-contained: store + workflow + tick loop |
| **Schedule** | PG Storable | Cron config + embedded task list |
| **Run** | PG Storable | Execution record with task results |
| **DAGRunner** | ThreadPoolExecutor | Parallel task execution by level |
| **resolve_fn** | importlib | Durable function references |

---

## Quick Start

```bash
pip install -e "."
python3 demo_scheduler.py
```

### Decorator (simplest)

```python
from scheduler import schedule

@schedule("*/5 * * * *")
def ingest_events():
    print("Ingesting events...")

# Pipeline — shared name groups into one Schedule
@schedule("0 2 * * *", name="etl")
def extract():
    return db.query("SELECT * FROM raw_events")

@schedule("0 2 * * *", name="etl", depends_on=["extract"])
def transform():
    return db.query("INSERT INTO clean_events SELECT ...")

@schedule("0 2 * * *", name="etl", depends_on=["transform"])
def load():
    return lakehouse.ingest("events", df)
```

### Programmatic

```python
from scheduler import Scheduler, Schedule, Task

# Single function
scheduler.register(Schedule(
    name="ingest",
    cron_expr="*/5 * * * *",
    tasks=[Task("ingest", fn="my_jobs:ingest_events")],
))

# Pipeline
scheduler.register(Schedule(
    name="etl",
    cron_expr="0 2 * * *",
    tasks=[
        Task("extract", fn="jobs:extract"),
        Task("transform", fn="jobs:transform", depends_on=["extract"]),
        Task("load", fn="jobs:load", depends_on=["transform"]),
    ],
))

# Management
scheduler.fire("etl")                  # manual trigger
scheduler.pause("etl")                # pause
scheduler.resume("etl")               # resume
runs = scheduler.history("etl")       # query past runs
schedules = scheduler.list_schedules() # list all
```

---

## Models

### Schedule (Storable)

The only top-level concept. Always has a `tasks` list.

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Unique schedule name |
| `cron_expr` | str | Cron expression (`*/5 * * * *`) |
| `tasks` | list[Task] | Embedded task list |
| `description` | str | Human-readable description |
| `max_retries` | int | Max retries on failure |
| `timeout_s` | int | Default timeout per task |

State machine: `ACTIVE` ↔ `PAUSED` → `DELETED`

### Task (Embedded)

Lives inside `Schedule.tasks`. Not persisted independently.

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Task name (unique within schedule) |
| `fn` | str | Importable path (`module:qualname`) |
| `depends_on` | list[str] | Task names this depends on |
| `timeout_s` | int | Timeout in seconds |
| `retries` | int | Per-task retries |
| `enabled` | bool | Skip if False |

### Run (Storable)

Execution record. Created per schedule fire.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | str | UUID (auto-generated) |
| `schedule_name` | str | Which schedule fired |
| `started_at` | str | ISO timestamp |
| `finished_at` | str | ISO timestamp |
| `result` | str | Summary (`all_succeeded`, `has_failures`, `empty`) |
| `error` | str | Top-level error if any |
| `task_results` | dict | task_name → TaskResult |
| `retries_left` | int | Remaining retries |

State machine: `PENDING` → `RUNNING` → `SUCCESS` / `PARTIAL` / `ERROR` → `RETRYING` → `RUNNING`

### TaskResult (Embedded)

Lives inside `Run.task_results`.

| Field | Type | Description |
|-------|------|-------------|
| `task_name` | str | Which task |
| `status` | str | `SUCCESS`, `ERROR`, `SKIPPED` |
| `result` | str | Return value (stringified) |
| `error` | str | Error message |
| `duration_ms` | float | Execution time |

---

## Execution

### DAG Runner

Tasks execute level-by-level with parallel branches:

```
Level 0:  [extract]           ← no dependencies, runs first
Level 1:  [transform, audit]  ← both depend on extract, run in parallel
Level 2:  [load]              ← depends on transform, runs after level 1
```

- **Failure propagation**: if a task fails, all downstream dependents are `SKIPPED`
- **Partial success**: if some tasks succeed and some fail, Run state = `PARTIAL`
- **Disabled tasks**: `enabled=False` tasks are excluded from execution order
- **Cycle detection**: `CycleError` raised if task graph has cycles

### Function Resolution

`Task.fn` stores an importable Python path as `module:qualname`:

```python
"my_jobs:ingest_events"           # module-level function
"my_jobs:ETL.extract"             # class method
"tests._sched_fixtures:fn_ok"     # test fixture
```

The server resolves these via `importlib` at execution time — crash-durable. After a restart, functions are re-resolved from the stored path.

### WorkflowEngine Integration

When a `WorkflowEngine` is provided, each task executes via `engine.step()` for checkpointed crash recovery. Without an engine, tasks run directly.

---

## API Boundaries

| Layer | Import | What |
|-------|--------|------|
| **User** | `from scheduler import ...` | `Scheduler`, `Schedule`, `Task`, `Run`, `TaskResult`, `CycleError`, `@schedule` |
| **Platform** | `from scheduler.admin import ...` | `SchedulerServer` |
| **Internal** | never imported directly | `server.py`, `client.py`, `dag_runner.py`, `dag.py`, `resolve.py`, `cron.py`, `_registry.py` |

### Platform Setup

```python
from scheduler.admin import SchedulerServer
from scheduler import Scheduler

# SchedulerServer is self-contained: embedded PG + WorkflowEngine
server = SchedulerServer(data_dir="data/scheduler")
server.start()                    # starts PG, engine, tick loop
server.register_alias("demo")

# Flush decorator-registered schedules to PG
import my_jobs  # triggers @schedule decorators
server.collect_schedules()

# User code
scheduler = Scheduler("demo")
scheduler.fire("etl")
```

---

## Cron Expressions

Standard 5-field cron (`minute hour dom month dow`):

| Expression | Meaning |
|-----------|---------|
| `*/5 * * * *` | Every 5 minutes |
| `*/1 * * * *` | Every minute |
| `0 * * * *` | Every hour |
| `0 2 * * *` | Daily at 02:00 UTC |
| `0 0 * * 0` | Weekly on Sunday at 00:00 |
| `0 0 1,15 * *` | 1st and 15th of month |

### Utilities

```python
from scheduler.cron import next_fire, prev_fire, is_due, validate, describe

next_fire("*/5 * * * *")                    # next fire time
prev_fire("*/5 * * * *")                    # most recent fire time
is_due("*/5 * * * *", last_fire=last)       # should we fire now?
validate("*/5 * * * *")                     # True if valid
describe("*/5 * * * *")                     # "every 5 minutes"
```

---

## Test Coverage

71 tests covering:

| Category | Tests | What |
|----------|-------|------|
| Embedded | 5 | Reactive wiring, serialization, write guard |
| Models | 10 | Task, Schedule, Run creation + serialization + state machines |
| Cron | 11 | next/prev fire, is_due, validate, describe |
| DAG graph | 7 | Acyclicity, execution order, cycle detection, disabled tasks |
| DAG runner | 7 | Linear, parallel, failure/skip, disabled, duration, empty |
| Decorators | 3 | Register, default name, depends_on |
| resolve_fn | 5 | Module resolution, nested attrs, error cases |
| Integration (PG) | 10 | Write/read, state transitions, register+fire, tick, pipeline |
| Full-stack (PG+Engine) | 8 | Single-task, pipeline, diamond, failure, tick, pause, duration |
