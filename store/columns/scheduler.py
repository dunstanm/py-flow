"""
Scheduler columns — cron, DAG, run, and task fields.

Used by Schedule, DAG, Run Storables and TaskDef, TaskResult Embeddeds.
"""

from store.columns import REGISTRY

# ── Schedule fields ──────────────────────────────────────────────

REGISTRY.define("cron_expr", str,
    description="Cron expression for scheduling (e.g. '*/5 * * * *')",
    semantic_type="label",
    role="attribute",
    display_name="Cron Expression",
)

REGISTRY.define("target_fn", str,
    description="Dotted path or registered name of the target function",
    semantic_type="label",
    role="attribute",
    display_name="Target Function",
)

REGISTRY.define("target_args", dict,
    description="Arguments to pass to the target function",
    semantic_type="label",
    role="attribute",
    nullable=True,
)

REGISTRY.define("dag_name", str,
    description="Name of the DAG to execute",
    semantic_type="label",
    role="dimension",
    display_name="DAG Name",
)

REGISTRY.define("run_type", str,
    description="Type of run: 'function' or 'dag'",
    semantic_type="label",
    role="dimension",
    enum=["function", "dag"],
    display_name="Run Type",
)

REGISTRY.define("max_retries", int,
    description="Maximum number of retry attempts",
    semantic_type="count",
    role="attribute",
    display_name="Max Retries",
)

REGISTRY.define("timeout_s", int,
    description="Timeout in seconds",
    semantic_type="count",
    role="attribute",
    unit="seconds",
    display_name="Timeout (s)",
)

# ── DAG / Task fields ───────────────────────────────────────────

REGISTRY.define("description", str,
    description="Human-readable description",
    semantic_type="free_text",
    role="attribute",
    nullable=True,
)

REGISTRY.define("tasks", list,
    description="List of embedded task definitions",
    semantic_type="label",
    role="attribute",
    nullable=True,
)

REGISTRY.define("depends_on", list,
    description="List of task names this task depends on",
    semantic_type="label",
    role="attribute",
    nullable=True,
)

REGISTRY.define("retries", int,
    description="Number of retry attempts for a task",
    semantic_type="count",
    role="attribute",
)

REGISTRY.define("enabled", bool,
    description="Whether this task is enabled",
    semantic_type="label",
    role="attribute",
)

# ── Run fields ───────────────────────────────────────────────────

REGISTRY.define("run_id", str,
    description="Unique identifier for a run execution",
    semantic_type="identifier",
    role="dimension",
    display_name="Run ID",
)

REGISTRY.define("schedule_name", str,
    description="Name of the schedule that triggered this run",
    semantic_type="label",
    role="dimension",
    display_name="Schedule Name",
)

REGISTRY.define("started_at", str,
    description="ISO timestamp when execution started",
    semantic_type="timestamp",
    role="attribute",
    display_name="Started At",
)

REGISTRY.define("finished_at", str,
    description="ISO timestamp when execution finished",
    semantic_type="timestamp",
    role="attribute",
    display_name="Finished At",
)

REGISTRY.define("result", str,
    description="Execution result summary",
    semantic_type="free_text",
    role="attribute",
    nullable=True,
)

REGISTRY.define("error", str,
    description="Error message if execution failed",
    semantic_type="free_text",
    role="attribute",
    nullable=True,
)

REGISTRY.define("workflow_id", str,
    description="WorkflowEngine handle ID for durable execution",
    semantic_type="identifier",
    role="attribute",
    display_name="Workflow ID",
)

REGISTRY.define("task_results", dict,
    description="Map of task_name to TaskResult for DAG runs",
    semantic_type="label",
    role="attribute",
    nullable=True,
)

REGISTRY.define("retries_left", int,
    description="Remaining retry attempts",
    semantic_type="count",
    role="attribute",
)

# ── TaskResult fields ────────────────────────────────────────────

REGISTRY.define("task_name", str,
    description="Name of the task within a DAG",
    semantic_type="label",
    role="dimension",
    display_name="Task Name",
)

REGISTRY.define("duration_ms", float,
    description="Task execution duration in milliseconds",
    semantic_type="count",
    role="measure",
    unit="milliseconds",
    display_name="Duration (ms)",
)
