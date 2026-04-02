import pytest

from app.db.models.task import TaskStatus
from app.services.task_runner.state_machine import can_transition, transition_or_raise


def test_valid_state_machine_transition() -> None:
    assert can_transition(TaskStatus.received, TaskStatus.triaged) is True
    assert transition_or_raise(TaskStatus.testing, TaskStatus.ready_for_pr) == TaskStatus.ready_for_pr


def test_invalid_state_machine_transition() -> None:
    with pytest.raises(ValueError):
        transition_or_raise(TaskStatus.received, TaskStatus.done)
