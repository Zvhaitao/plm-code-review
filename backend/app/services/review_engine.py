"""Claude / 兼容端点评审引擎:输入 diff,输出结构化 findings。

为兼容第三方 Anthropic 兼容端点(如代理 grok 等模型),不依赖 Anthropic
专有的 messages.parse / output_config / adaptive thinking,而是用普通
messages.create 并要求模型返回 JSON,再稳健解析。
"""
from __future__ import annotations

import json
import re

import anthropic
from pydantic import BaseModel, Field, ValidationError

from ..config import get_settings
from ..prompts.review_system import build_system_prompt, build_user_message

# diff 过长时截断的安全阈值(字符数)
MAX_DIFF_CHARS = 120_000


class LLMFinding(BaseModel):
    file_path: str = Field(default="")
    line: int | None = Field(default=None)
    severity: str = Field(default="info")
    category: str = Field(default="")
    message: str = Field(default="")
    suggestion: str = Field(default="")
    existing_code: str = Field(default="")


class LLMReviewResult(BaseModel):
    summary: str = Field(default="")
    score: int = Field(default=0)
    findings: list[LLMFinding] = Field(default_factory=list)
    tool_summary: str = Field(default="")  # 引擎评审过程摘要(如 ocr 工具调用统计)


class ReviewEngineError(RuntimeError):
    pass


def _truncate_diff(diff: str) -> str:
    if len(diff) <= MAX_DIFF_CHARS:
        return diff
    return diff[:MAX_DIFF_CHARS] + "\n\n[diff 过长已截断,仅评审前一部分]"


def _build_client() -> anthropic.Anthropic:
    settings = get_settings()
    kwargs: dict = {}
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
    if settings.anthropic_auth_token:
        kwargs["auth_token"] = settings.anthropic_auth_token
    elif settings.anthropic_api_key:
        kwargs["api_key"] = settings.anthropic_api_key
    else:
        raise ReviewEngineError("未配置 ANTHROPIC_API_KEY 或 ANTHROPIC_AUTH_TOKEN")
    return anthropic.Anthropic(**kwargs)


def _extract_json(text: str) -> dict:
    """从模型输出中稳健提取 JSON 对象(容忍 ```json 代码块/前后缀文本)。"""
    text = text.strip()
    # 去掉 markdown 代码围栏
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 退化:截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ReviewEngineError("模型未返回可解析的 JSON")


def run_claude_review(
    repo_full_name: str,
    pr_title: str,
    diff: str,
    review_rules: str = "",
    *,
    client: anthropic.Anthropic | None = None,
) -> LLMReviewResult:
    """调用模型对 diff 进行评审,返回结构化结果。`client` 可注入用于测试。"""
    settings = get_settings()
    if not diff.strip():
        return LLMReviewResult(summary="没有可评审的代码变更。", score=100, findings=[])

    if client is None:
        client = _build_client()

    system_prompt = build_system_prompt(review_rules)
    user_message = build_user_message(repo_full_name, pr_title, _truncate_diff(diff))

    try:
        response = client.messages.create(
            model=settings.review_model,
            max_tokens=settings.claude_max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        raise ReviewEngineError(f"模型调用失败: {exc}") from exc

    text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    if not text.strip():
        raise ReviewEngineError("模型返回为空")

    data = _extract_json(text)
    try:
        return LLMReviewResult.model_validate(data)
    except ValidationError as exc:
        raise ReviewEngineError(f"评审结果结构不符合预期: {exc}") from exc
