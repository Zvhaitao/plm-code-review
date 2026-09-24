"""ESLint 静态检查服务(平台自带 ESLint,不依赖目标仓库配置)。

对本次提交改动到的可 lint 文件,取"提交时刻"的完整内容,送给 backend/eslint-runner
的 node 运行器做检查。best-effort:node 不可用 / 运行失败均抛 LintNotAvailable,
由调用方决定是否忽略(评审主流程不因此失败)。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from .git_service import FileChange

logger = logging.getLogger(__name__)

# 可静态检查的文件后缀
LINTABLE_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}

# eslint-runner 所在目录(backend/eslint-runner)
_RUNNER_DIR = Path(__file__).resolve().parents[2] / "eslint-runner"
_RUNNER_SCRIPT = _RUNNER_DIR / "runner.mjs"

# 兜底的 node 路径(与前端一致的 nvm 安装)
_FALLBACK_NODE = r"C:\Users\94924\AppData\Roaming\nvm\v20.19.0\node.exe"

# ESLint 9 要求的最低 Node 主版本
_MIN_NODE_MAJOR = 18

# 单文件内容过大则跳过(避免拖垮 lint)
_MAX_FILE_CHARS = 400_000

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class LintNotAvailable(RuntimeError):
    """node / 运行器不可用,或运行器整体失败。"""


@dataclass
class LintFinding:
    file_path: str
    line: int | None
    column: int | None
    rule_id: str
    severity: str  # error / warning
    message: str
    on_changed_line: bool
    rule_desc: str = ""
    rule_url: str = ""
    code_context: str = ""
    context_start: int | None = None


# 代码片段:问题行前后各取的行数
_CONTEXT_RADIUS = 3


def _node_major(bin_path: str) -> int | None:
    """返回 node 主版本号(如 20),无法确定返回 None。"""
    try:
        proc = subprocess.run(
            [bin_path, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    m = re.match(r"v?(\d+)\.", proc.stdout.strip())
    return int(m.group(1)) if m else None


def _node_bin() -> str:
    """定位一个可用(主版本 >= 18)的 node:settings.node_bin → PATH → 兜底 nvm 路径。

    系统里可能装了旧 node(如 v14,ESLint 9 无法运行),因此需校验版本。
    """
    settings = get_settings()
    candidates: list[str] = []
    if settings.node_bin:
        resolved = shutil.which(settings.node_bin) or settings.node_bin
        candidates.append(resolved)
    which = shutil.which("node")
    if which:
        candidates.append(which)
    candidates.append(_FALLBACK_NODE)

    tried: list[str] = []
    for cand in candidates:
        if not cand or cand in tried:
            continue
        tried.append(cand)
        if not (shutil.which(cand) or os.path.isfile(cand)):
            continue
        major = _node_major(cand)
        if major is not None and major >= _MIN_NODE_MAJOR:
            return cand
    raise LintNotAvailable(
        f"未找到 Node {_MIN_NODE_MAJOR}+(ESLint 9 需要);"
        "可在 .env 设置 NODE_BIN 指向合适的 node 可执行文件"
    )


def _git_file_content(local_path: str, commit_sha: str, path: str) -> str | None:
    """取某提交下某文件的完整内容。失败返回 None。"""
    if not (local_path and commit_sha and path):
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", local_path, "show", f"{commit_sha}:{path}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _added_line_numbers(patch: str) -> set[int]:
    """从 unified diff 的 patch 解析出新增(+)行在新文件里的行号集合。"""
    added: set[int] = set()
    if not patch:
        return added
    new_no = 0
    for line in patch.split("\n"):
        m = _HUNK_RE.match(line)
        if m:
            new_no = int(m.group(1))
            continue
        if not line:
            continue
        c = line[0]
        if c == "+":
            added.add(new_no)
            new_no += 1
        elif c == "-":
            pass  # 删除行不推进新文件行号
        elif c == "\\":
            pass  # "\ No newline at end of file"
        else:
            new_no += 1  # 上下文行
    return added


def _is_lintable(fc: FileChange) -> bool:
    if fc.status == "deleted" or fc.binary:
        return False
    return Path(fc.path).suffix.lower() in LINTABLE_EXTS


def lint_commit(local_path: str, commit_sha: str, files: list[FileChange]) -> list[LintFinding]:
    """对本次提交改动的可 lint 文件跑 ESLint,返回问题列表。

    没有可 lint 文件时返回空列表;node / 运行器不可用时抛 LintNotAvailable。
    """
    if not _RUNNER_SCRIPT.is_file():
        raise LintNotAvailable(f"eslint 运行器不存在: {_RUNNER_SCRIPT}(需先在 eslint-runner 目录 npm install)")

    targets = [fc for fc in files if _is_lintable(fc)]
    if not targets:
        return []

    payload_files = []
    added_by_path: dict[str, set[int]] = {}
    lines_by_path: dict[str, list[str]] = {}
    for fc in targets:
        content = _git_file_content(local_path, commit_sha, fc.path)
        if content is None or len(content) > _MAX_FILE_CHARS:
            continue
        payload_files.append({"path": fc.path, "content": content})
        added_by_path[fc.path] = _added_line_numbers(fc.patch)
        lines_by_path[fc.path] = content.splitlines()

    if not payload_files:
        return []

    node = _node_bin()
    try:
        proc = subprocess.run(
            [node, str(_RUNNER_SCRIPT)],
            input=json.dumps({"files": payload_files}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            cwd=str(_RUNNER_DIR),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LintNotAvailable(f"运行 eslint 失败: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise LintNotAvailable(f"eslint 运行器返回非零: {detail}")

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise LintNotAvailable(f"解析 eslint 输出失败: {exc}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise LintNotAvailable(f"eslint 运行器错误: {data['error']}")

    findings: list[LintFinding] = []
    rules_meta = data.get("rulesMeta", {}) if isinstance(data, dict) else {}
    for result in data.get("results", []):
        path = result.get("path", "")
        added = added_by_path.get(path, set())
        src_lines = lines_by_path.get(path, [])
        for m in result.get("messages", []):
            line = m.get("line")
            severity = "error" if m.get("severity") == 2 else "warning"
            rule_id = m.get("ruleId") or ""
            meta = rules_meta.get(rule_id, {}) if rule_id else {}
            ctx_start, ctx_code = _code_snippet(src_lines, line)
            findings.append(
                LintFinding(
                    file_path=path,
                    line=line,
                    column=m.get("column"),
                    rule_id=rule_id,
                    severity=severity,
                    message=m.get("message") or "",
                    on_changed_line=bool(line and line in added),
                    rule_desc=meta.get("description", "") if isinstance(meta, dict) else "",
                    rule_url=meta.get("url", "") if isinstance(meta, dict) else "",
                    code_context=ctx_code,
                    context_start=ctx_start,
                )
            )
    return findings


def _code_snippet(lines: list[str], line: int | None) -> tuple[int | None, str]:
    """取问题行前后各 _CONTEXT_RADIUS 行,返回(片段首行行号, 片段文本)。"""
    if not lines or not line or line < 1:
        return None, ""
    start = max(1, line - _CONTEXT_RADIUS)
    end = min(len(lines), line + _CONTEXT_RADIUS)
    if end < start:
        return None, ""
    snippet = "\n".join(lines[start - 1 : end])
    return start, snippet
