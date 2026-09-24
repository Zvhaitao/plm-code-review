"""Pydantic 请求 / 响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# --- 认证 ---
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str


# --- 仓库 ---
class RepositoryCreate(BaseModel):
    gitea_owner: str
    gitea_name: str
    local_path: str
    branch: str = ""
    enabled: bool = True
    review_rules: str = ""


class RepositoryUpdate(BaseModel):
    local_path: str | None = None
    branch: str | None = None
    enabled: bool | None = None
    review_rules: str | None = None


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    gitea_owner: str
    gitea_name: str
    local_path: str
    branch: str
    last_reviewed_sha: str
    enabled: bool
    review_rules: str
    created_at: datetime


# --- 评审 ---
class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_path: str
    line: int | None
    severity: str
    category: str
    message: str
    suggestion: str
    existing_code: str = ""


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    repository_id: int
    repository_name: str = ""
    commit_sha: str
    commit_message: str
    commit_author: str
    status: str
    stage: str = ""
    stage_detail: str = ""
    tool_summary: str = ""
    trigger: str
    model: str
    summary: str
    score: int | None
    error: str
    created_at: datetime
    finished_at: datetime | None


class ReviewDetailOut(ReviewOut):
    findings: list[FindingOut] = []


class CheckResult(BaseModel):
    repository_id: int
    created_review_ids: list[int]
    message: str


# --- 提交改动(diff) ---
class FileDiffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    path: str
    old_path: str = ""
    status: str  # added / modified / deleted / renamed
    additions: int = 0
    deletions: int = 0
    patch: str = ""
    binary: bool = False
    truncated: bool = False


class CommitDiffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sha: str
    parent_sha: str = ""
    author: str = ""
    message: str = ""
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    files: list[FileDiffOut] = []


# --- 分类维度 ---
class RepoFacet(BaseModel):
    id: int
    name: str
    review_count: int


class AuthorFacet(BaseModel):
    name: str
    review_count: int


class ReviewFacets(BaseModel):
    repositories: list[RepoFacet] = []
    authors: list[AuthorFacet] = []
    pending_count: int = 0  # 待处理(pending)评审数,用于"处理未完成"入口
