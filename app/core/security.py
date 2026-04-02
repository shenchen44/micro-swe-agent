import hashlib
import hmac


def verify_github_webhook_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
