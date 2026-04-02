import pytest

from app.services.task_runner.orchestrator import create_task_from_webhook


def test_task_deduplication(db_session, sample_issue_payload: dict) -> None:
    first = create_task_from_webhook(db_session, sample_issue_payload)
    assert first.id
    with pytest.raises(ValueError, match="active_task_exists"):
        create_task_from_webhook(db_session, sample_issue_payload)
