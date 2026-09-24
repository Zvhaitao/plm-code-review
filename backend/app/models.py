"""ORM 数据模型。"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("gitea_owner", "gitea_name", name="uq_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gitea_owner: Mapped[str] = mapped_column(String(128), index=True)  # 展示用名称(组/前缀)
    gitea_name: Mapped[str] = mapped_column(String(128), index=True)   # 展示用名称(仓库)
    local_path: Mapped[str] = mapped_column(String(1024), default="")  # 本地已克隆的仓库路径
    branch: Mapped[str] = mapped_column(String(128), default="")       # 目标分支,空=当前分支
    last_reviewed_sha: Mapped[str] = mapped_column(String(64), default="")  # 评审基线
    enabled: Mapped[bool] = mapped_column(default=True)
    review_rules: Mapped[str] = mapped_column(Text, default="")  # 自然语言规则/关注点
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    reviews: Mapped[list["Review"]] = relationship(back_populates="repository", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.gitea_owner}/{self.gitea_name}"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(64), default="", index=True)
    commit_message: Mapped[str] = mapped_column(String(1024), default="")
    commit_author: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/succeeded/failed
    stage: Mapped[str] = mapped_column(String(32), default="")  # 运行阶段:preparing/reviewing/parsing(结束清空)
    stage_detail: Mapped[str] = mapped_column(String(300), default="")  # 运行中实时活动(来自 ocr 输出)
    tool_summary: Mapped[str] = mapped_column(Text, default="")  # 评审过程摘要(引擎工具调用统计)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual/scheduled
    model: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100 总体评分
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="reviews")
    findings: Mapped[list["Finding"]] = relationship(back_populates="review", cascade="all, delete-orphan")

    @property
    def repository_name(self) -> str:
        return self.repository.full_name if self.repository else ""


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(512), default="")
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info/warning/error
    category: Mapped[str] = mapped_column(String(64), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    existing_code: Mapped[str] = mapped_column(Text, default="")  # 原代码片段(用于对比展示)

    review: Mapped["Review"] = relationship(back_populates="findings")
