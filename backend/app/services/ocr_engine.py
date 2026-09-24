"""接入 Alibaba open-code-review(`ocr` CLI)的评审引擎。

对指定本地仓库的某个提交调用:
    ocr review --repo <path> -c <sha> --format json --audience agent
解析其 JSON 输出,映射为平台的 LLMReviewResult(summary/score/findings)。

ocr 使用它自身配置的 LLM(`ocr config` / `ocr llm test`),与后端的
ANTHROPIC_* 相互独立。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
from collections.abc import Callable

from ..config import get_settings
from .review_engine import LLMFinding, LLMReviewResult, ReviewEngineError

logger = logging.getLogger(__name__)

# ocr 的 severity(high/medium/low)→ 平台 severity(error/warning/info)
_SEVERITY_MAP = {
    "high": "error",
    "critical": "error",
    "blocker": "error",
    "medium": "warning",
    "moderate": "warning",
    "low": "info",
    "minor": "info",
    "info": "info",
}
# 计分权重:满分 100 依据各 finding 扣分
_SCORE_WEIGHT = {"error": 20, "warning": 10, "info": 3}

# ocr 进度行形如:"[ocr]   ✘ code_search failed: ..." / "[ocr]  ✔ file_read ..."
_ACTIVITY_RE = re.compile(r"^\[ocr\]\s*(.+)$")
# 工具名 → 中文
_TOOL_LABELS = {
    "file_read": "读取文件",
    "file_find": "查找文件",
    "code_search": "搜索代码",
    "list_dir": "浏览目录",
}


class OcrNotAvailable(ReviewEngineError):
    """ocr CLI 未安装 / 不在 PATH。"""


def _clean_activity(line: str) -> str:
    """从 ocr stderr 行提取可展示的活动文本;非进度行返回空串。"""
    m = _ACTIVITY_RE.match(line.strip())
    if not m:
        return ""
    text = m.group(1).strip()
    # 去掉前导的 ✔/✘/• 等符号
    text = text.lstrip("✔✘•·-* \t")
    return text[:280]


def _format_tool_summary(data: dict) -> str:
    """把 ocr 的 tool_calls 统计转成一句中文过程摘要。"""
    tc = data.get("tool_calls")
    if not isinstance(tc, dict):
        return ""
    by_tool = tc.get("by_tool") or {}
    if not isinstance(by_tool, dict) or not by_tool:
        return ""
    fail_by = tc.get("failure_by_tool") or {}
    parts = []
    for tool, cnt in by_tool.items():
        label = _TOOL_LABELS.get(tool, tool)
        seg = f"{label} ×{cnt}"
        fails = fail_by.get(tool) if isinstance(fail_by, dict) else None
        if fails:
            seg += f"({fails} 失败)"
        parts.append(seg)
    total = tc.get("total")
    head = f"共 {total} 次工具调用:" if total else ""
    return head + " · ".join(parts)


def _map_severity(raw: str) -> str:
    return _SEVERITY_MAP.get((raw or "").strip().lower(), "warning")


def _compute_score(findings: list[LLMFinding]) -> int:
    penalty = sum(_SCORE_WEIGHT.get(f.severity, 10) for f in findings)
    return max(0, min(100, 100 - penalty))


def _build_summary(data: dict, findings: list[LLMFinding]) -> str:
    if not findings:
        return "open-code-review 未发现问题。"
    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    n_info = sum(1 for f in findings if f.severity == "info")
    parts = []
    if n_err:
        parts.append(f"{n_err} 个严重")
    if n_warn:
        parts.append(f"{n_warn} 个警告")
    if n_info:
        parts.append(f"{n_info} 个提示")
    return f"open-code-review 共发现 {len(findings)} 条问题(" + "、".join(parts) + ")。"


def _git_file_at_commit(local_path: str, commit_sha: str, path: str) -> list[str] | None:
    """取某提交下某文件的全部行(用于重建 EXISTING CODE)。失败返回 None。"""
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
    return proc.stdout.splitlines()


def _existing_code_for(
    c: dict, cache: dict[str, list[str] | None], local_path: str, commit_sha: str
) -> str:
    """comment 的 EXISTING CODE:模型已给则用模型的;否则按行号区间从源码重建。"""
    given = (c.get("existing_code") or "").strip()
    if given:
        return c["existing_code"]
    path = c.get("path", "")
    start = c.get("start_line")
    end = c.get("end_line") or start
    if not path or not isinstance(start, int) or start < 1:
        return ""
    if path not in cache:
        cache[path] = _git_file_at_commit(local_path, commit_sha, path)
    lines = cache[path]
    if not lines:
        return ""
    if not isinstance(end, int) or end < start:
        end = start
    # 行号 1-based 且闭区间;做边界保护
    snippet = lines[start - 1 : min(end, len(lines))]
    return "\n".join(snippet)


def _parse_result(data: dict, local_path: str = "", commit_sha: str = "") -> LLMReviewResult:
    findings: list[LLMFinding] = []
    src_cache: dict[str, list[str] | None] = {}
    for c in data.get("comments", []):
        suggestion = c.get("suggestion_code") or ""
        findings.append(
            LLMFinding(
                file_path=c.get("path", ""),
                line=c.get("start_line"),
                severity=_map_severity(c.get("severity", "")),
                category=c.get("category", ""),
                message=c.get("content", ""),
                suggestion=suggestion,
                existing_code=_existing_code_for(c, src_cache, local_path, commit_sha),
            )
        )
    return LLMReviewResult(
        summary=_build_summary(data, findings),
        score=_compute_score(findings),
        findings=findings,
        tool_summary=_format_tool_summary(data),
    )


def _resolve_bin(name: str) -> str:
    """解析 ocr 可执行文件。Windows 上 npm 全局命令是 ocr.cmd,
    直接把裸名 'ocr' 交给 subprocess 会找不到,需用 shutil.which 解析
    (会遵循 PATHEXT,匹配到 .cmd/.exe)。"""
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise OcrNotAvailable(
        f"未找到 ocr CLI(ocr_bin={name!r})。请先安装 "
        "@alibaba-group/open-code-review 并确保在 PATH 中。"
    )


def run_ocr_review(
    local_path: str,
    commit_sha: str,
    review_rules: str = "",
    on_activity: Callable[[str], None] | None = None,
) -> tuple[LLMReviewResult, str]:
    """对 local_path 仓库的 commit_sha 提交调用 ocr 评审。

    返回 (评审结果, ocr 实际使用的模型名)。失败抛 ReviewEngineError;
    ocr 不可用时抛 OcrNotAvailable(供上层回退到内置引擎)。

    on_activity: 可选回调,ocr 运行中每产生一条进度行时被调用(用于实时展示)。
    """
    settings = get_settings()
    ocr_bin = _resolve_bin(settings.ocr_bin)
    cmd = [
        ocr_bin,
        "review",
        "--repo",
        local_path,
        "-c",
        commit_sha,
        "--format",
        "json",
        "--audience",
        "agent",
    ]
    if review_rules.strip():
        cmd += ["--background", review_rules.strip()]

    timeout = max(1, settings.ocr_timeout_minutes) * 60
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise OcrNotAvailable(
            f"未找到 ocr CLI(ocr_bin={settings.ocr_bin!r})。请先安装 "
            "@alibaba-group/open-code-review 并确保在 PATH 中。"
        ) from exc

    # 后台线程逐行读取 stderr:既收集完整错误信息,又把进度行回调出去
    stderr_chunks: list[str] = []

    def _pump_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_chunks.append(line)
            if on_activity:
                act = _clean_activity(line)
                if act:
                    try:
                        on_activity(act)
                    except Exception:  # noqa: BLE001  进度回调不能影响主流程
                        logger.debug("on_activity 回调异常(忽略)", exc_info=True)

    t = threading.Thread(target=_pump_stderr, daemon=True)
    t.start()

    # 超时看门狗:到点强杀,避免无限阻塞
    timed_out = {"v": False}

    def _kill_on_timeout() -> None:
        timed_out["v"] = True
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass

    watchdog = threading.Timer(timeout, _kill_on_timeout)
    watchdog.start()
    try:
        assert proc.stdout is not None
        out = proc.stdout.read()  # 阻塞直到进程结束(EOF)
        proc.wait()
    finally:
        watchdog.cancel()
        t.join(timeout=2)

    if timed_out["v"]:
        raise ReviewEngineError(f"ocr 评审超时(>{settings.ocr_timeout_minutes} 分钟)")

    if proc.returncode != 0:
        detail = ("".join(stderr_chunks) or out or "").strip()[:500]
        raise ReviewEngineError(f"ocr 评审失败(exit={proc.returncode}): {detail}")

    out = (out or "").strip()
    if not out:
        raise ReviewEngineError("ocr 未返回任何输出")

    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        # 极少数情况下 stdout 前面混入非 JSON 行,退化截取
        start = out.find("{")
        if start == -1:
            raise ReviewEngineError(f"ocr 输出非 JSON: {out[:200]}") from exc
        data = json.loads(out[start:])

    model = (data.get("llm") or {}).get("model", "") or "open-code-review"
    return _parse_result(data, local_path=local_path, commit_sha=commit_sha), model
