from dataclasses import dataclass
import json

from app.services.openai.client import OpenAIChatClient
from app.services.openai.prompts import SYSTEM_PROMPT
from app.services.openai.tools import AgentToolbox


@dataclass(slots=True)
class AgentRunResult:
    summary: dict
    patch_text: str
    pr_title: str
    pr_body_summary: dict
    raw_response: str = ""
    model_call_count: int = 0
    tool_call_count: int = 0


class AgentResponseParseError(ValueError):
    def __init__(self, message: str, raw_response: str) -> None:
        super().__init__(message)
        self.raw_response = raw_response


def _extract_fenced_json(text: str) -> str | None:
    marker = "```"
    start = text.find(marker)
    while start != -1:
        end = text.find(marker, start + len(marker))
        if end == -1:
            break
        block = text[start + len(marker):end].strip()
        if block.startswith("json"):
            block = block[4:].lstrip()
        if block.startswith("{") and block.endswith("}"):
            return block
        start = text.find(marker, end + len(marker))
    return None


def _find_json_object_span(text: str) -> tuple[int, int] | None:
    in_string = False
    escape = False
    depth = 0
    start = -1
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start != -1:
                return start, index + 1
    return None


def extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if not cleaned:
        raise AgentResponseParseError("empty_model_response", text)

    candidates = [cleaned]
    fenced = _extract_fenced_json(cleaned)
    if fenced is not None:
        candidates.insert(0, fenced)

    span = _find_json_object_span(cleaned)
    if span is not None:
        candidates.append(cleaned[span[0]:span[1]])

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise AgentResponseParseError(f"invalid_model_json: {cleaned[:500]}", text)


class AgentLoop:
    """OpenAI-compatible chat-completions loop with explicit tool dispatch."""

    def __init__(self, client: OpenAIChatClient | None = None) -> None:
        self.client = client or OpenAIChatClient()

    def run(self, toolbox: AgentToolbox) -> AgentRunResult:
        model_call_count = 0
        tool_call_count = 0
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Investigate the issue, use tools as needed, prefer read_file plus write_file for minimal edits, "
                    "run tests after changes, and return strict JSON with keys summary, patch_text, pr_title, pr_body_summary.\n\n"
                    f"issue_context:\n{json.dumps(toolbox.get_issue_context(), ensure_ascii=False, indent=2)}"
                ),
            },
        ]

        while True:
            response = self.client.create_completion(messages=messages, tools=toolbox.tool_schemas())
            model_call_count += 1
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls or []
            tool_call_count += len(tool_calls)
            if not tool_calls:
                break

            assistant_message = {
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ],
            }
            messages.append(assistant_message)

            for call in tool_calls:
                result = toolbox.dispatch(call.function.name, call.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        payload = response_message.content or ""
        parsed = extract_json_object(payload)
        return AgentRunResult(
            summary=parsed.get("summary") or {},
            patch_text=parsed.get("patch_text") or "",
            pr_title=parsed.get("pr_title") or "fix: resolve issue",
            pr_body_summary=parsed.get("pr_body_summary") or {},
            raw_response=payload,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
        )
