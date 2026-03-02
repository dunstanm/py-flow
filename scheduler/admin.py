"""
scheduler.admin — Platform API for Scheduler Infrastructure
=============================================================
Start/stop the scheduler server, flush decorated schedules.

Platform usage::

    from scheduler.admin import SchedulerServer

    server = SchedulerServer(data_dir="data/scheduler")
    server.start()
    server.register_alias("demo")
    server.collect_schedules()   # flush @schedule-decorated functions to PG

User code uses ``Scheduler("demo")`` from ``scheduler``.
"""

from scheduler.server import SchedulerServer

__all__ = ["SchedulerServer"]
