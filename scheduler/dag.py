"""
DAG graph helpers — acyclicity validation, execution order, task lookup.

Operates on Schedule instances with embedded Task lists.
"""

from __future__ import annotations

from collections import defaultdict, deque

from scheduler.models import Schedule, Task


class CycleError(Exception):
    """Raised when a DAG contains a cycle."""

    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        super().__init__(f"Cycle detected in DAG: {' → '.join(cycle_path)}")


def get_task(sched: Schedule, name: str) -> Task | None:
    """Look up a Task by name from the embedded tasks list.

    Returns None if not found.
    """
    for t in sched.task_defs:
        if t.name == name:
            return t
    return None


def validate_acyclic(sched: Schedule) -> list[str]:
    """Topological sort via Kahn's algorithm. Raises CycleError if cycle detected.

    Returns the full topological order (flat list of task names).
    Only considers enabled tasks.
    """
    tasks = [t for t in sched.task_defs if t.enabled]
    task_names = {t.name for t in tasks}

    # Build adjacency and in-degree
    in_degree: dict[str, int] = {t.name: 0 for t in tasks}
    dependents: dict[str, list[str]] = defaultdict(list)

    for t in tasks:
        for dep in t.depends_on:
            if dep in task_names:
                in_degree[t.name] += 1
                dependents[dep].append(t.name)

    # Start with tasks that have no dependencies
    queue = deque(name for name, deg in in_degree.items() if deg == 0)
    order = []

    while queue:
        name = queue.popleft()
        order.append(name)
        for child in dependents[name]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(order) != len(tasks):
        # Find cycle for error message
        remaining = [t.name for t in tasks if t.name not in set(order)]
        raise CycleError(remaining)

    return order


def execution_order(sched: Schedule) -> list[list[str]]:
    """Return task names grouped by level for parallel execution.

    Level 0: enabled tasks with no dependencies (or deps all disabled).
    Level 1: enabled tasks whose deps are all in level 0.
    etc.

    Validates acyclicity first. Raises CycleError if cycle detected.
    """
    tasks = [t for t in sched.task_defs if t.enabled]
    if not tasks:
        return []

    task_names = {t.name for t in tasks}

    # Validate first
    validate_acyclic(sched)

    # Build dependency map (only enabled deps)
    deps: dict[str, set[str]] = {}
    for t in tasks:
        deps[t.name] = {d for d in t.depends_on if d in task_names}

    assigned: set[str] = set()
    levels: list[list[str]] = []

    while len(assigned) < len(tasks):
        level = [
            name for name, task_deps in deps.items()
            if name not in assigned and task_deps <= assigned
        ]
        if not level:
            # Should not happen if validate_acyclic passed
            break
        levels.append(sorted(level))
        assigned.update(level)

    return levels
