from types import SimpleNamespace

import pytest

from app.services.openai.agent_loop import AgentLoop, AgentResponseParseError, extract_json_object


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


def test_agent_loop_reports_model_and_tool_call_counts() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def create_completion(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content="",
                                tool_calls=[
                                    SimpleNamespace(
                                        id="call-1",
                                        function=SimpleNamespace(name="get_issue_context", arguments="{}"),
                                    )
                                ],
                            )
                        )
                    ]
                )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"summary": {}, "patch_text": "", "pr_title": "x", "pr_body_summary": {}}',
                            tool_calls=[],
                        )
                    )
                ]
            )

    class FakeToolbox:
        @staticmethod
        def tool_schemas():
            return []

        @staticmethod
        def get_issue_context():
            return {"title": "x"}

        @staticmethod
        def dispatch(name: str, arguments_json: str):
            assert name == "get_issue_context"
            assert arguments_json == "{}"
            return {"title": "x"}

    result = AgentLoop(client=FakeClient()).run(FakeToolbox())

    assert result.model_call_count == 2
    assert result.tool_call_count == 1
