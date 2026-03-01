"""
Cron expression utilities — croniter is an implementation detail.

All public functions accept/return str and datetime only.
No croniter types leak into the public API.
"""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter


def next_fire(cron_expr: str, after: datetime | None = None) -> datetime:
    """Return the next fire time for a cron expression.

    Args:
        cron_expr: Cron expression string (e.g. "*/5 * * * *").
        after: Base time. Defaults to now (UTC).

    Returns:
        Next fire time as a timezone-aware UTC datetime.
    """
    base = after or datetime.now(timezone.utc)
    cron = croniter(cron_expr, base)
    return cron.get_next(datetime).replace(tzinfo=timezone.utc)


def prev_fire(cron_expr: str, before: datetime | None = None) -> datetime:
    """Return the most recent fire time for a cron expression.

    Args:
        cron_expr: Cron expression string.
        before: Base time. Defaults to now (UTC).

    Returns:
        Previous fire time as a timezone-aware UTC datetime.
    """
    base = before or datetime.now(timezone.utc)
    cron = croniter(cron_expr, base)
    return cron.get_prev(datetime).replace(tzinfo=timezone.utc)


def is_due(cron_expr: str, last_fire: datetime | None, now: datetime | None = None) -> bool:
    """Check if a schedule should fire now.

    Returns True if there is at least one fire time between last_fire and now.

    Args:
        cron_expr: Cron expression string.
        last_fire: When this schedule last fired. None = never fired.
        now: Current time. Defaults to now (UTC).
    """
    now = now or datetime.now(timezone.utc)
    if last_fire is None:
        return True
    nxt = next_fire(cron_expr, after=last_fire)
    return nxt <= now


def validate(cron_expr: str) -> bool:
    """Check if a cron expression is syntactically valid.

    Returns True if valid, False otherwise.
    """
    try:
        croniter(cron_expr)
        return True
    except (ValueError, KeyError, TypeError):
        return False


def describe(cron_expr: str) -> str:
    """Return a human-readable description of a cron expression.

    Examples:
        "*/5 * * * *" → "every 5 minutes"
        "0 * * * *"   → "every hour"
        "0 2 * * *"   → "daily at 02:00"
        "0 0 * * 0"   → "weekly on Sunday at 00:00"
    """
    parts = cron_expr.strip().split()
    if len(parts) < 5:
        return cron_expr

    minute, hour, dom, month, dow = parts[:5]

    # Every N minutes
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
        n = minute[2:]
        return f"every {n} minutes" if n != "1" else "every minute"

    # Every N hours
    if minute == "0" and hour.startswith("*/") and dom == "*" and month == "*" and dow == "*":
        n = hour[2:]
        return f"every {n} hours" if n != "1" else "every hour"

    # Every hour at :00
    if minute == "0" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return "every hour"

    # Daily at HH:MM
    if hour.isdigit() and minute.isdigit() and dom == "*" and month == "*" and dow == "*":
        return f"daily at {int(hour):02d}:{int(minute):02d}"

    # Weekly
    dow_names = {
        "0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
        "4": "Thursday", "5": "Friday", "6": "Saturday", "7": "Sunday",
    }
    if hour.isdigit() and minute.isdigit() and dom == "*" and month == "*" and dow in dow_names:
        return f"weekly on {dow_names[dow]} at {int(hour):02d}:{int(minute):02d}"

    return cron_expr
