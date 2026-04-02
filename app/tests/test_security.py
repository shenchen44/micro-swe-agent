import hashlib
import hmac

from app.core.security import verify_github_webhook_signature


def test_verify_github_webhook_signature() -> None:
    payload = b'{"hello":"world"}'
    secret = "test-secret"
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_github_webhook_signature(secret, payload, signature) is True
    assert verify_github_webhook_signature(secret, payload, "sha256=bad") is False
