"""
Scheduler client (internal module).

Public import via ``scheduler``::

    from scheduler import Scheduler
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from scheduler.models import Schedule, Run

if TYPE_CHECKING:
    from scheduler.server import SchedulerServer

logger = logging.getLogger(__name__)


class Scheduler:
    """User-facing scheduler API.

    Provides registration, triggering, management, and query operations.
    Data operations use StoreClient (PG). Execution delegates to SchedulerServer.
    """

    def __init__(self, client, server: SchedulerServer):
        """
        Args:
            client: StoreClient instance for persisting Schedules, DAGs, and Runs.
            server: SchedulerServer instance for execution (same process).
        """
        self._client = client
        self._server = server

    # ── Registration ──────────────────────────────────────────────────

    def register(self, schedule: Schedule) -> Schedule:
        """Register a schedule (persists to PG via StoreClient).

        Returns the schedule with entity_id populated.
        """
        entity_id = self._client.write(schedule)
        logger.info("Registered schedule '%s' (%s) → %s",
                     schedule.name, schedule.cron_expr, entity_id)
        return schedule

    # ── Trigger ───────────────────────────────────────────────────────

    def fire(self, name: str) -> Run:
        """Manually trigger a schedule by name (ad-hoc run).

        Delegates execution to SchedulerServer.execute_run().
        Returns the completed Run with final state.

        Raises ValueError if schedule not found.
        """
        sched = self._find_schedule(name)
        if sched is None:
            raise ValueError(f"Schedule '{name}' not found")
        return self._server.execute_run(sched)

    def tick(self, now=None) -> list[Run]:
        """Delegate to server tick (check due schedules, fire any that are due).

        Returns list of Runs that were started.
        """
        return self._server.tick(now)

    # ── Management ────────────────────────────────────────────────────

    def pause(self, name: str) -> Schedule:
        """Pause a schedule (ACTIVE → PAUSED)."""
        sched = self._find_schedule(name)
        if sched is None:
            raise ValueError(f"Schedule '{name}' not found")
        self._client.transition(sched, "PAUSED")
        return sched

    def resume(self, name: str) -> Schedule:
        """Resume a schedule (PAUSED → ACTIVE)."""
        sched = self._find_schedule(name)
        if sched is None:
            raise ValueError(f"Schedule '{name}' not found")
        self._client.transition(sched, "ACTIVE")
        return sched

    def delete(self, name: str) -> Schedule:
        """Soft-delete a schedule (→ DELETED)."""
        sched = self._find_schedule(name)
        if sched is None:
            raise ValueError(f"Schedule '{name}' not found")
        self._client.transition(sched, "DELETED")
        return sched

    # ── Query ─────────────────────────────────────────────────────────

    def list_schedules(self) -> list[Schedule]:
        """Return all non-deleted schedules."""
        all_schedules = self._client.query(Schedule)
        return [s for s in all_schedules if s._store_state != "DELETED"]

    def history(self, name: str, limit: int = 20) -> list[Run]:
        """Return past runs for a schedule, most recent first."""
        all_runs = self._client.query(Run, filters={"schedule_name": name})
        matching = list(all_runs)
        matching.sort(key=lambda r: r.started_at, reverse=True)
        return matching[:limit]

    # ── Internal ──────────────────────────────────────────────────────

    def _find_schedule(self, name: str) -> Optional[Schedule]:
        """Find a schedule by name."""
        results = self._client.query(Schedule, filters={"name": name})
        items = list(results)
        return items[0] if items else None
