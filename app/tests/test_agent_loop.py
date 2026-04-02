import pytest

from app.services.openai.agent_loop import AgentResponseParseError, extract_json_object


def test_extract_json_object_from_plain_json() -> None:
    parsed = extract_json_object('{"summary": {}, "patch_text": "", "pr_title": "x", "pr_body_summary": {}}')
    assert parsed["pr_title"] == "x"


def test_extract_json_object_from_fenced_json() -> None:
    parsed = extract_json_object('```json\n{"summary": {}, "patch_text": "", "pr_title": "x", "pr_body_summary": {}}\n```')
    assert parsed["pr_title"] == "x"


def test_extract_json_object_from_wrapped_text() -> None:
    parsed = extract_json_object('Here is the result:\n{"summary": {}, "patch_text": "", "pr_title": "x", "pr_body_summary": {}}\nThanks')
    assert parsed["pr_title"] == "x"


def test_extract_json_object_empty_response_has_clear_error() -> None:
    with pytest.raises(AgentResponseParseError, match="empty_model_response"):
        extract_json_object("")


def test_extract_json_object_invalid_response_includes_snippet() -> None:
    with pytest.raises(AgentResponseParseError, match="invalid_model_json: definitely not json"):
        extract_json_object("definitely not json")
