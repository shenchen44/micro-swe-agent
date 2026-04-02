from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(slots=True)
class IssueTriggerDecision:
    should_process: bool
    reason: str


def extract_label_names(issue_payload: dict) -> set[str]:
    labels = issue_payload.get("labels", [])
    return {label.get("name", "").strip().lower() for label in labels if label.get("name")}


def should_process_issue_event(event: str, action: str, payload: dict) -> IssueTriggerDecision:
    if event != "issues":
        return IssueTriggerDecision(False, "unsupported_event")

    issue = payload.get("issue") or {}
    if issue.get("pull_request"):
        return IssueTriggerDecision(False, "issue_is_pull_request")
    if not (issue.get("body") or "").strip():
        return IssueTriggerDecision(False, "empty_body")

    settings = get_settings()
    target_labels = settings.target_labels
    issue_labels = extract_label_names(issue)

    if action == "opened":
        if issue_labels & target_labels:
            return IssueTriggerDecision(True, "opened_with_target_label")
        return IssueTriggerDecision(False, "opened_without_target_label")

    if action == "labeled":
        new_label = ((payload.get("label") or {}).get("name") or "").strip().lower()
        if new_label in target_labels:
            return IssueTriggerDecision(True, "labeled_with_target_label")
        return IssueTriggerDecision(False, "non_target_label")

    if action == "edited" and issue_labels & target_labels:
        return IssueTriggerDecision(True, "edited_with_target_label")

    return IssueTriggerDecision(False, f"unsupported_action:{action}")
