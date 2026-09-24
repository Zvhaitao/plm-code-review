"""本地 git 仓库操作(仓库已提前克隆到本地)。

用 subprocess 调 git,避免额外依赖。所有命令用 `git -C <path>`。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


class GitError(RuntimeError):
    pass


def _run(path: str, args: list[str], timeout: int = 120) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GitError("未找到 git 命令,请确认已安装 git") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git 命令超时: {' '.join(args)}") from exc
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} 失败")
    return proc.stdout


@dataclass
class Commit:
    sha: str
    message: str
    author: str


def pull(path: str, branch: str = "") -> None:
    """拉取远端最新。branch 为空则拉当前分支。"""
    if branch:
        _run(path, ["checkout", branch])
    _run(path, ["pull", "--ff-only"], timeout=180)


def head_sha(path: str, branch: str = "") -> str:
    ref = branch or "HEAD"
    return _run(path, ["rev-parse", ref]).strip()


def new_commits(path: str, since_sha: str, branch: str = "") -> list[Commit]:
    """返回 since_sha 之后到 HEAD 的提交(按时间从旧到新)。

    since_sha 为空时(首次接入),只返回最新一条提交,避免评审整个历史。
    """
    ref = branch or "HEAD"
    if not since_sha:
        rng = [ref, "-1"]
    else:
        rng = [f"{since_sha}..{ref}"]
    # 用不可见分隔符解析:sha \x1f message \x1f author \x1e
    fmt = "%H%x1f%s%x1f%an%x1e"
    out = _run(path, ["log", "--reverse", f"--pretty=format:{fmt}", *rng])
    commits: list[Commit] = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) >= 3:
            commits.append(Commit(sha=parts[0], message=parts[1], author=parts[2]))
    return commits


def commit_diff(path: str, sha: str) -> str:
    """单个提交相对其父提交的 diff。"""
    return _run(path, ["show", "--format=", "--no-color", sha], timeout=180)
