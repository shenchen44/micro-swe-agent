from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import verify_github_webhook_signature
from app.db.session import get_db
from app.services.github.webhooks import should_process_issue_event
from app.services.task_runner.orchestrator import create_task_from_webhook

router = APIRouter(prefix="/webhooks/github", tags=["github"])


@router.post("")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    payload_bytes = await request.body()
    if not verify_github_webhook_signature(settings.github_webhook_secret, payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_signature")

    payload = await request.json()
    decision = should_process_issue_event(x_github_event, payload.get("action", ""), payload)
    if not decision.should_process:
        return {"status": "ignored", "reason": decision.reason}

    try:
        task = create_task_from_webhook(db, payload)
    except ValueError as exc:
        if str(exc) == "active_task_exists":
            return {"status": "ignored", "reason": "active_task_exists"}
        raise

    return {"status": "accepted", "task_id": task.id}
