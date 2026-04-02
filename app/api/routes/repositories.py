from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.repository import Repository
from app.db.session import get_db
from app.schemas.repositories import RepositoryRead

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
def list_repositories(db: Session = Depends(get_db)) -> list[Repository]:
    return list(db.scalars(select(Repository).order_by(Repository.created_at.desc())))
