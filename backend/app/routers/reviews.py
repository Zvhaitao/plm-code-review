"""评审路由:列表 / 详情 / 立即检查(受登录保护)。"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import get_current_user
from ..config import get_settings
from ..db import get_db
from ..models import Repository, Review
from ..schemas import (
    AuthorFacet,
    CheckResult,
    CommitDiffOut,
    RepoFacet,
    ReviewDetailOut,
    ReviewFacets,
    ReviewOut,
)
from ..services.git_service import GitError, commit_changes
from ..services.worker import check_repository, process_pending_reviews, run_review

router = APIRouter(prefix="/api/reviews", tags=["reviews"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ReviewOut])
def list_reviews(
    db: Session = Depends(get_db),
    repository_id: int | None = Query(default=None),
    commit_author: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    stmt = (
        select(Review)
        .options(selectinload(Review.repository))
        .order_by(Review.created_at.desc())
        .limit(limit)
    )
    if repository_id is not None:
        stmt = stmt.where(Review.repository_id == repository_id)
    if commit_author:
        stmt = stmt.where(Review.commit_author == commit_author)
    else:
        hidden = get_settings().hidden_authors
        if hidden:
            stmt = stmt.where(Review.commit_author.notin_(hidden))
    return db.scalars(stmt).all()


@router.get("/facets", response_model=ReviewFacets)
def review_facets(db: Session = Depends(get_db)):
    """分类维度:各仓库、各提交人的评审数量,用于前端筛选。"""
    hidden = get_settings().hidden_authors
    repo_rows = db.execute(
        select(Repository.id, Repository.gitea_owner, Repository.gitea_name, func.count(Review.id))
        .outerjoin(Review, Review.repository_id == Repository.id)
        .group_by(Repository.id)
        .order_by(func.count(Review.id).desc())
    ).all()
    author_stmt = (
        select(Review.commit_author, func.count(Review.id))
        .where(Review.commit_author != "")
        .group_by(Review.commit_author)
        .order_by(func.count(Review.id).desc())
    )
    if hidden:
        author_stmt = author_stmt.where(Review.commit_author.notin_(hidden))
    author_rows = db.execute(author_stmt).all()
    pending_stmt = select(func.count(Review.id)).where(Review.status == "pending")
    if hidden:
        pending_stmt = pending_stmt.where(Review.commit_author.notin_(hidden))
    pending_count = db.scalar(pending_stmt) or 0
    return ReviewFacets(
        repositories=[
            RepoFacet(id=rid, name=f"{owner}/{name}", review_count=cnt)
            for rid, owner, name, cnt in repo_rows
        ],
        authors=[AuthorFacet(name=author, review_count=cnt) for author, cnt in author_rows],
        pending_count=pending_count,
    )


@router.post("/process-pending", response_model=CheckResult, status_code=status.HTTP_202_ACCEPTED)
def process_pending(background: BackgroundTasks, db: Session = Depends(get_db)):
    """处理所有未完成(pending)评审:后台串行执行(含上次中断后被重置的)。"""
    ids = list(
        db.scalars(select(Review.id).where(Review.status == "pending").order_by(Review.id)).all()
    )
    if ids:
        background.add_task(process_pending_reviews)
    return CheckResult(
        repository_id=0,
        created_review_ids=ids,
        message=f"已开始处理 {len(ids)} 条未完成评审" if ids else "没有待处理的评审",
    )


@router.post("/{review_id}/rerun", response_model=ReviewOut, status_code=status.HTTP_202_ACCEPTED)
def rerun_review(review_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """重新评审单条(用于失败 / 中断 / 需要重跑的记录)。"""
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评审不存在")
    review.status = "pending"
    review.stage = ""
    review.stage_detail = ""
    review.error = ""
    review.finished_at = None
    db.commit()
    db.refresh(review)
    background.add_task(run_review, review_id)
    return review


@router.get("/{review_id}/diff", response_model=CommitDiffOut)
def get_review_diff(review_id: int, db: Session = Depends(get_db)):
    """本次提交相对父提交的改动(结构化 diff,供前端展示)。"""
    review = db.scalar(
        select(Review).where(Review.id == review_id).options(selectinload(Review.repository))
    )
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评审不存在")
    repo = review.repository
    if repo is None or not repo.local_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该仓库未配置本地路径")
    try:
        changes = commit_changes(repo.local_path, review.commit_sha)
    except GitError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"读取提交改动失败: {exc}"
        ) from exc
    return changes


@router.get("/{review_id}", response_model=ReviewDetailOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    review = db.scalar(
        select(Review).where(Review.id == review_id).options(selectinload(Review.findings))
    )
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评审不存在")
    return review


@router.post("/check/{repository_id}", response_model=CheckResult, status_code=status.HTTP_202_ACCEPTED)
def check_now(repository_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """立即检查仓库:git pull → 对每个新提交发起评审(后台执行)。"""
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="仓库不存在")
    if not repo.local_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该仓库未配置本地路径")

    background.add_task(check_repository, repo.id, trigger="manual")
    return CheckResult(
        repository_id=repo.id,
        created_review_ids=[],
        message="已开始检查,新提交的评审将在后台生成,请稍后刷新看板",
    )
