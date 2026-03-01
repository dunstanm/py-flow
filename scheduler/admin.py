"""
scheduler.admin — Platform API for Scheduler Infrastructure
=============================================================
Start/stop the scheduler server, flush decorated schedules to PG.

Platform usage::

    from scheduler.admin import SchedulerServer, collect_schedules

    server = SchedulerServer(engine, client)
    scheduler = Scheduler(client, server)
    collect_schedules(scheduler)   # flush @schedule-decorated functions to PG
    server.start()                 # background tick loop
    server.stop()

User code uses ``Scheduler(client, server)`` from ``scheduler``.
"""

from scheduler.server import SchedulerServer
from scheduler.decorators import collect_schedules

__all__ = ["SchedulerServer", "collect_schedules"]
