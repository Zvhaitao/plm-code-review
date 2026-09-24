"""后台评审任务(本地 pull 模式)。

check_repository: git pull → 找出新提交 → 每个新提交建一条 Review 并评审。
run_review: 对单条 Review(已含 commit_sha)取 diff → 调模型 → 落库。
结果只存平台,不回帖。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Finding, Repository, Review
from .git_service import GitError, commit_diff, head_sha, new_commits, pull
from .ocr_engine import OcrNotAvailable, run_ocr_review
from .review_engine import ReviewEngineError, run_claude_review

logger = logging.getLogger(__name__)


def reset_orphaned_reviews() -> int:
    """启动时把上次进程中断遗留的 running 评审重置为 pending(可被重新处理)。

    进程被杀 / 重启时,正在跑的评审会永远停在 running。启动时统一重置,
    使其可通过"处理未完成"重新评审。返回重置条数。
    """
    db = SessionLocal()
    try:
        orphaned = db.scalars(select(Review).where(Review.status == "running")).all()
        for r in orphaned:
            r.status = "pending"
            r.stage = ""
            r.stage_detail = ""
        if orphaned:
            db.commit()
            logger.info("启动重置了 %s 条中断的评审(running → pending)", len(orphaned))
        return len(orphaned)
    finally:
        db.close()


def process_pending_reviews() -> list[int]:
    """依次执行当前所有 pending 评审(串行,避免并发打爆模型端)。返回处理的 id 列表。"""
    db = SessionLocal()
    try:
        ids = list(
            db.scalars(select(Review.id).where(Review.status == "pending").order_by(Review.id)).all()
        )
    finally:
        db.close()
    for rid in ids:
        run_review(rid)
    return ids


def check_repository(repo_id: int, *, trigger: str = "manual") -> list[int]:
    """拉取仓库并为每个新提交创建并执行评审。返回创建的 review id 列表。"""
    db = SessionLocal()
    created: list[int] = []
    try:
        repo = db.get(Repository, repo_id)
        if repo is None or not repo.local_path:
            logger.warning("check_repository: 仓库 %s 不存在或未配置本地路径", repo_id)
            return created

        # 先 pull(失败不致命,继续用本地已有提交)
        try:
            pull(repo.local_path, repo.branch)
        except GitError as exc:
            logger.warning("git pull 失败(继续用本地状态): %s", exc)

        try:
            commits = new_commits(repo.local_path, repo.last_reviewed_sha, repo.branch)
        except GitError as exc:
            logger.error("读取新提交失败: %s", exc)
            return created

        for c in commits:
            review = Review(
                repository_id=repo.id,
                commit_sha=c.sha,
                commit_message=c.message,
                commit_author=c.author,
                status="pending",
                trigger=trigger,
            )
            db.add(review)
            db.commit()
            db.refresh(review)
            created.append(review.id)

        # 更新基线到当前 HEAD
        try:
            repo.last_reviewed_sha = head_sha(repo.local_path, repo.branch)
            db.commit()
        except GitError:
            pass
    finally:
        db.close()

    # 逐个执行评审(串行,避免并发打爆模型端)
    for rid in created:
        run_review(rid)
    return created


def _make_activity_reporter(review_id: int):
    """返回一个节流的进度回调:把 ocr 运行中的活动写入 Review.stage_detail。

    运行在 ocr 的 stderr 读取线程里,因此用独立的短会话,best-effort,
    异常一律吞掉,绝不影响评审主流程。"""
    state = {"last": 0.0, "text": ""}

    def report(activity: str) -> None:
        now = time.monotonic()
        if activity == state["text"] or now - state["last"] < 1.2:
            return
        state["last"] = now
        state["text"] = activity
        try:
            s = SessionLocal()
            try:
                r = s.get(Review, review_id)
                if r is not None and r.status == "running":
                    r.stage_detail = activity
                    s.commit()
            finally:
                s.close()
        except Exception:  # noqa: BLE001
            logger.debug("写入 stage_detail 失败(忽略)", exc_info=True)

    return report


def run_review(review_id: int) -> None:
    """对单条 Review 执行评审。异常记录到 Review.error。"""
    db = SessionLocal()
    try:
        review = db.get(Review, review_id)
        if review is None:
            return
        review.status = "running"
        review.stage = "preparing"
        review.stage_detail = ""
        db.commit()

        repo = review.repository
        from ..config import get_settings

        settings = get_settings()

        # 评审引擎:优先 ocr(Alibaba open-code-review);不可用时回退内置引擎。
        result = None
        model_used = ""
        if settings.review_engine == "ocr":
            review.stage = "reviewing"
            db.commit()
            try:
                result, model_used = run_ocr_review(
                    local_path=repo.local_path,
                    commit_sha=review.commit_sha,
                    review_rules=repo.review_rules,
                    on_activity=_make_activity_reporter(review.id),
                )
            except OcrNotAvailable as exc:
                logger.warning("ocr 引擎不可用,回退内置引擎: %s", exc)
            except ReviewEngineError as exc:
                _fail(db, review, str(exc))
                return

        if result is None:  # builtin 引擎或 ocr 回退
            review.stage = "reviewing"
            db.commit()
            try:
                diff = commit_diff(repo.local_path, review.commit_sha)
            except GitError as exc:
                _fail(db, review, f"取 diff 失败: {exc}")
                return
            try:
                result = run_claude_review(
                    repo_full_name=repo.full_name,
                    pr_title=review.commit_message,
                    diff=diff,
                    review_rules=repo.review_rules,
                )
                model_used = settings.review_model
            except ReviewEngineError as exc:
                _fail(db, review, str(exc))
                return

        review.stage = "parsing"
        review.stage_detail = ""
        db.commit()

        review.summary = result.summary
        review.score = result.score
        review.model = model_used
        review.tool_summary = getattr(result, "tool_summary", "") or ""
        review.findings.clear()
        for lf in result.findings:
            review.findings.append(
                Finding(
                    file_path=lf.file_path,
                    line=lf.line,
                    severity=lf.severity,
                    category=lf.category,
                    message=lf.message,
                    suggestion=lf.suggestion,
                    existing_code=getattr(lf, "existing_code", ""),
                )
            )
        review.status = "succeeded"
        review.stage = ""
        review.stage_detail = ""
        review.finished_at = datetime.now(timezone.utc)
        review.error = ""
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("run_review 未预期异常 review_id=%s", review_id)
        review = db.get(Review, review_id)
        if review is not None:
            _fail(db, review, "内部错误,详见服务日志")
    finally:
        db.close()


def _fail(db, review: Review, message: str) -> None:
    review.status = "failed"
    review.stage = ""
    review.stage_detail = ""
    review.error = message
    review.finished_at = datetime.now(timezone.utc)
    db.commit()
    logger.error("评审失败 review_id=%s: %s", review.id, message)
