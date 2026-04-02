from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepositoryRead(BaseModel):
    id: int
    github_repo_id: int
    owner: str
    name: str
    default_branch: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
