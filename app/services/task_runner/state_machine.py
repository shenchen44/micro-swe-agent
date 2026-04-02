from app.db.models.task import TaskStatus


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.received: {TaskStatus.triaged, TaskStatus.failed},
    TaskStatus.triaged: {TaskStatus.sandbox_ready, TaskStatus.failed},
    TaskStatus.sandbox_ready: {TaskStatus.patching, TaskStatus.failed},
    TaskStatus.patching: {TaskStatus.testing, TaskStatus.retrying, TaskStatus.failed},
    TaskStatus.testing: {TaskStatus.retrying, TaskStatus.ready_for_pr, TaskStatus.failed},
    TaskStatus.retrying: {TaskStatus.patching, TaskStatus.failed},
    TaskStatus.ready_for_pr: {TaskStatus.pr_opened, TaskStatus.failed},
    TaskStatus.pr_opened: {TaskStatus.done, TaskStatus.failed},
    TaskStatus.done: set(),
    TaskStatus.failed: set(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition_or_raise(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    if not can_transition(current, target):
        raise ValueError(f"Invalid task status transition: {current} -> {target}")
    return target
