"""本地 git 仓库操作(仓库已提前克隆到本地)。

用 subprocess 调 git,避免额外依赖。所有命令用 `git -C <path>`。
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class GitError(RuntimeError):
    pass


# 解析 "diff --git a/<old> b/<new>"
_DIFF_GIT_RE = re.compile(r'^diff --git "?a/(.+?)"? "?b/(.+?)"?$')


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


# 单文件 patch 超过此字符数则截断(避免超大改动拖垮前端)
_MAX_FILE_PATCH_CHARS = 60000


@dataclass
class FileChange:
    path: str
    old_path: str  # 重命名时的旧路径,否则与 path 相同
    status: str  # added / modified / deleted / renamed
    additions: int
    deletions: int
    patch: str  # 从首个 @@ 开始的 hunk 文本;二进制/纯重命名可能为空
    binary: bool
    truncated: bool


@dataclass
class CommitChanges:
    sha: str
    parent_sha: str
    author: str
    message: str
    files_changed: int
    insertions: int
    deletions: int
    files: list[FileChange]


def _parse_file_block(block: str) -> FileChange | None:
    """解析一段以 'diff --git' 开头的文件 diff 块。"""
    lines = block.splitlines()
    if not lines:
        return None

    old_path = ""
    new_path = ""
    status = "modified"
    binary = False
    hunk_start = None  # 首个 @@ 行索引

    for i, ln in enumerate(lines):
        if ln.startswith("--- "):
            p = ln[4:].strip()
            old_path = "" if p == "/dev/null" else p[2:] if p.startswith(("a/", "b/")) else p
        elif ln.startswith("+++ "):
            p = ln[4:].strip()
            new_path = "" if p == "/dev/null" else p[2:] if p.startswith(("a/", "b/")) else p
        elif ln.startswith("new file mode"):
            status = "added"
        elif ln.startswith("deleted file mode"):
            status = "deleted"
        elif ln.startswith("rename from "):
            status = "renamed"
            old_path = ln[len("rename from "):].strip()
        elif ln.startswith("rename to "):
            new_path = ln[len("rename to "):].strip()
        elif ln.startswith("Binary files") or ln.startswith("GIT binary patch"):
            binary = True
        elif ln.startswith("@@") and hunk_start is None:
            hunk_start = i
            break  # 头部信息已解析完,剩余是 hunk

    # 从 "diff --git a/x b/y" 兜底取路径
    if not new_path or not old_path:
        first = lines[0]
        m = _DIFF_GIT_RE.match(first)
        if m:
            old_path = old_path or m.group(1)
            new_path = new_path or m.group(2)

    path = new_path or old_path
    if status == "deleted":
        path = old_path or new_path

    additions = deletions = 0
    patch = ""
    if hunk_start is not None:
        hunk_lines = lines[hunk_start:]
        for ln in hunk_lines:
            if ln.startswith("+") and not ln.startswith("+++"):
                additions += 1
            elif ln.startswith("-") and not ln.startswith("---"):
                deletions += 1
        patch = "\n".join(hunk_lines)

    truncated = False
    if len(patch) > _MAX_FILE_PATCH_CHARS:
        patch = patch[:_MAX_FILE_PATCH_CHARS] + "\n… (diff 过大,已截断)"
        truncated = True

    if not path:
        return None
    return FileChange(
        path=path,
        old_path=old_path or path,
        status=status,
        additions=additions,
        deletions=deletions,
        patch=patch,
        binary=binary,
        truncated=truncated,
    )


def commit_changes(path: str, sha: str) -> CommitChanges:
    """结构化的提交改动:元信息 + 每个文件的 diff(供前端渲染)。"""
    meta = _run(
        path,
        ["show", "-s", "--format=%H%x1f%P%x1f%an%x1f%s", sha],
    ).strip()
    parts = meta.split("\x1f")
    full_sha = parts[0].strip() if len(parts) > 0 else sha
    parents = parts[1].strip() if len(parts) > 1 else ""
    author = parts[2].strip() if len(parts) > 2 else ""
    message = parts[3].strip() if len(parts) > 3 else ""
    parent_sha = parents.split()[0] if parents else ""

    raw = _run(path, ["show", "--format=", "--no-color", "-M", sha], timeout=180)
    files: list[FileChange] = []
    # 按 "diff --git" 切块(保留分隔符)
    blocks = re.split(r"(?m)^(?=diff --git )", raw)
    for block in blocks:
        if not block.strip().startswith("diff --git"):
            continue
        fc = _parse_file_block(block)
        if fc is not None:
            files.append(fc)

    return CommitChanges(
        sha=full_sha,
        parent_sha=parent_sha,
        author=author,
        message=message,
        files_changed=len(files),
        insertions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
        files=files,
    )
