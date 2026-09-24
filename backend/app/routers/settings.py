"""只读的运行时配置信息(不含密钥明文)。"""
from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..config import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])


@router.get("")
def read_settings():
    s = get_settings()
    return {
        "review_engine": s.review_engine,
        "review_model": s.review_model,
        "claude_max_tokens": s.claude_max_tokens,
        "anthropic_base_url": s.anthropic_base_url or "官方默认",
        "llm_configured": s.llm_configured,
        "poll_interval_minutes": s.poll_interval_minutes,
    }
