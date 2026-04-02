from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.task import Task, TaskStatus
from app.db.session import get_db
from app.schemas.tasks import TaskRead

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .options(selectinload(Task.attempts), selectinload(Task.artifacts))
            .order_by(Task.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: str, db: Session = Depends(get_db)) -> Task:
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.attempts), selectinload(Task.artifacts))
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task_not_found")
    return task


@router.post("/{task_id}/rerun", response_model=TaskRead)
def rerun_task(task_id: str, db: Session = Depends(get_db)) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task_not_found")
    if task.status not in {TaskStatus.failed, TaskStatus.done}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task_not_rerunnable")
    task.status = TaskStatus.triaged
    task.attempt_count = 0
    task.failure_reason = None
    task.branch_name = None
    task.base_commit = None
    task.head_commit = None
    task.pr_number = None
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
