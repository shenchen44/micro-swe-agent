from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    from app.main import app

    settings = get_settings()
    return {
        "status": "ok",
        "service": "micro-swe-agent",
        "version": app.version,
        "environment": settings.app_env,
        "dashboard_enabled": settings.dashboard_enabled,
    }
