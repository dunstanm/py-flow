"""
SchedulerServer — platform-side scheduler engine (internal).

Owns WorkflowEngine, DAGRunner, function resolution, and tick loop.
Users never import this directly.

Public import via ``scheduler.admin``::

    from scheduler.admin import SchedulerServer
"""

from __future__ import annotations

import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional

from scheduler.models import Schedule, Run, TaskResult
from scheduler.cron import is_due
from scheduler.dag_runner import DAGRunner

logger = logging.getLogger(__name__)


class SchedulerServer:
    """Platform-side scheduler: function resolution, DAG execution, tick loop.

    Users never import this directly. The platform creates a SchedulerServer
    at startup and passes it to the user-facing Scheduler client.
    """

    def __init__(self, engine, client):
        """
        Args:
            engine: WorkflowEngine instance for durable execution.
            client: StoreClient instance for persisting Schedules and Runs.
        """
        self._engine = engine
        self._client = client
        self._last_fire: dict[str, datetime] = {}
        self._dag_runner = DAGRunner(engine, client)
        self._poll_interval = 10.0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self, poll_interval: float = 10.0) -> None:
        """Start background tick loop in a daemon thread."""
        self._poll_interval = poll_interval
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("SchedulerServer started (poll=%.1fs)", poll_interval)

    def stop(self) -> None:
        """Stop the background tick loop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)
            self._thread = None
        logger.info("SchedulerServer stopped")

    def _run_loop(self) -> None:
        """Internal blocking loop — runs in background thread."""
        while self._running:
            try:
                runs = self.tick()
                if runs:
                    logger.info("Fired %d schedule(s): %s",
                                len(runs), [r.schedule_name for r in runs])
            except Exception:
                logger.exception("Tick failed")
            time.sleep(self._poll_interval)

    # ── Tick ───────────────────────────────────────────────────────────

    def tick(self, now: datetime | None = None) -> list[Run]:
        """Check all active schedules, fire any that are due.

        Returns list of Runs that were started.
        """
        now = now or datetime.now(timezone.utc)
        runs = []

        schedules = self._load_active_schedules()
        for sched in schedules:
            last = self._last_fire.get(sched.name)
            if is_due(sched.cron_expr, last, now=now):
                try:
                    run = self.execute_run(sched, now)
                    runs.append(run)
                except Exception:
                    logger.exception("Failed to fire schedule '%s'", sched.name)

        return runs

    # ── Execution ──────────────────────────────────────────────────────

    def execute_run(self, sched: Schedule, now: datetime | None = None) -> Run:
        """Execute a schedule and return the completed Run.

        Creates a Run, transitions PENDING → RUNNING → final,
        runs all tasks via DAGRunner.
        """
        now = now or datetime.now(timezone.utc)
        self._last_fire[sched.name] = now

        run = Run(
            schedule_name=sched.name,
            started_at=now.isoformat(),
            retries_left=sched.max_retries,
        )
        self._client.write(run)
        self._client.transition(run, "RUNNING")

        try:
            dag_run = self._dag_runner.run(sched)
            run.task_results = dag_run.task_results
            run.result = dag_run.result

            # Determine final state from task results
            if run.task_results:
                statuses = {tr.status if hasattr(tr, 'status') else tr.get('status', '')
                            for tr in run.task_results.values()}
                if "ERROR" in statuses:
                    final_state = "PARTIAL" if "SUCCESS" in statuses else "ERROR"
                else:
                    final_state = "SUCCESS"
            else:
                final_state = "SUCCESS"

            run.finished_at = datetime.now(timezone.utc).isoformat()
            self._client.update(run)
            self._client.transition(run, final_state)

        except Exception as e:
            run.error = str(e)
            run.finished_at = datetime.now(timezone.utc).isoformat()
            self._client.update(run)
            self._client.transition(run, "ERROR")
            logger.exception("Schedule '%s' run failed", sched.name)

        return run

    # ── Internal ───────────────────────────────────────────────────────

    def _load_active_schedules(self) -> list[Schedule]:
        """Load all schedules in ACTIVE state."""
        all_schedules = self._client.query(Schedule)
        return [s for s in all_schedules if s._store_state == "ACTIVE"]
