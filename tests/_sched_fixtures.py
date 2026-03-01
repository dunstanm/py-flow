"""
Importable test functions for scheduler tests.

These exist as module-level functions so resolve_fn("tests._sched_fixtures:fn_name")
can find them via importlib. Used by DAG runner and integration tests.
"""

import time

# ── Shared state for side-effect tracking ──────────────────────────────

call_log: list[str] = []


def reset_log():
    call_log.clear()


# ── Simple functions ───────────────────────────────────────────────────

def fn_return_a():
    call_log.append("a")
    return "done_a"


def fn_return_b():
    call_log.append("b")
    return "done_b"


def fn_return_c():
    call_log.append("c")
    return "done_c"


def fn_return_d():
    call_log.append("d")
    return "done_d"


# ── Functions for specific test scenarios ──────────────────────────────

def fn_slow():
    time.sleep(0.05)
    return "slow_done"


def fn_fast():
    return "fast_done"


def fn_boom():
    raise RuntimeError("boom")


def fn_ok():
    return "fine"


def fn_never():
    return "never_reached"


def fn_result_42():
    call_log.append("executed")
    return "result_42"


def fn_tick():
    call_log.append("ticked")
    return "ok"


def fn_pause():
    call_log.append("fired")
    return "paused_fn"
