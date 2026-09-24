"""仓库配置路由(受登录保护)。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Repository, User
from ..schemas import RepositoryCreate, RepositoryOut, RepositoryUpdate

router = APIRouter(prefix="/api/repositories", tags=["repositories"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[RepositoryOut])
def list_repositories(db: Session = Depends(get_db)):
    return db.scalars(select(Repository).order_by(Repository.created_at.desc())).all()


@router.post("", response_model=RepositoryOut, status_code=status.HTTP_201_CREATED)
def create_repository(payload: RepositoryCreate, db: Session = Depends(get_db)):
    exists = db.scalar(
        select(Repository).where(
            Repository.gitea_owner == payload.gitea_owner,
            Repository.gitea_name == payload.gitea_name,
        )
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该仓库已存在")
    repo = Repository(**payload.model_dump())
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@router.get("/{repo_id}", response_model=RepositoryOut)
def get_repository(repo_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="仓库不存在")
    return repo


@router.patch("/{repo_id}", response_model=RepositoryOut)
def update_repository(repo_id: int, payload: RepositoryUpdate, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="仓库不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(repo, field, value)
    db.commit()
    db.refresh(repo)
    return repo


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(repo_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="仓库不存在")
    db.delete(repo)
    db.commit()
