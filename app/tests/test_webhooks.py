from app.services.github.webhooks import should_process_issue_event


def test_issue_filter_accepts_opened_bug(sample_issue_payload: dict) -> None:
    decision = should_process_issue_event("issues", "opened", sample_issue_payload)
    assert decision.should_process is True


def test_issue_filter_rejects_empty_body(sample_issue_payload: dict) -> None:
    sample_issue_payload["issue"]["body"] = " "
    decision = should_process_issue_event("issues", "opened", sample_issue_payload)
    assert decision.should_process is False
    assert decision.reason == "empty_body"
