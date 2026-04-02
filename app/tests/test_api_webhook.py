import hashlib
import hmac
import json

from app.db.models.task import Task


def _signature(secret: str, payload: dict) -> str:
    raw = json.dumps(payload).encode()
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_webhook_creates_task(client, db_session, sample_issue_payload: dict) -> None:
    payload = sample_issue_payload
    raw = json.dumps(payload)
    signature = "sha256=" + hmac.new(b"test-secret", raw.encode(), hashlib.sha256).hexdigest()
    response = client.post(
        "/webhooks/github",
        content=raw,
        headers={"x-github-event": "issues", "x-hub-signature-256": signature, "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_webhook_invalid_signature(client, sample_issue_payload: dict) -> None:
    response = client.post(
        "/webhooks/github",
        json=sample_issue_payload,
        headers={"x-github-event": "issues", "x-hub-signature-256": "sha256=bad"},
    )
    assert response.status_code == 401
