"""
Scheduler — cron-based scheduling with durable task execution.

User API::

    from scheduler import Scheduler, Schedule, Task, Run, TaskResult
    from scheduler import schedule

    @schedule("*/5 * * * *")
    def ingest_events():
        Lakehouse("demo").sync_events()

    @schedule("0 2 * * *", name="etl")
    def extract(): ...

    @schedule("0 2 * * *", name="etl", depends_on=["extract"])
    def transform(): ...

Platform API lives in ``scheduler.admin``.
"""

from scheduler.models import Schedule, Task, Run, TaskResult
from scheduler.client import Scheduler
from scheduler.dag import CycleError
from scheduler.decorators import schedule

__all__ = [
    "Scheduler",
    "Schedule", "Task", "Run", "TaskResult",
    "CycleError",
    "schedule",
]
