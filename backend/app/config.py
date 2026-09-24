"""应用配置:从环境变量 / .env 读取。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Claude / 兼容端点 ---
    # 两种鉴权任选其一:api_key(x-api-key 头) 或 auth_token(Authorization: Bearer)
    anthropic_api_key: str = ""
    anthropic_auth_token: str = ""
    anthropic_base_url: str = ""  # 第三方兼容端点,如 https://true-sota.com;留空则用官方
    # 模型:ANTHROPIC_MODEL 优先,其次 ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL,最后 CLAUDE_MODEL
    claude_model: str = "claude-opus-5"
    anthropic_model: str = ""
    anthropic_default_haiku_model: str = ""
    anthropic_default_sonnet_model: str = ""
    anthropic_default_opus_model: str = ""
    claude_max_tokens: int = 16000

    @property
    def review_model(self) -> str:
        return (
            self.anthropic_model
            or self.anthropic_default_sonnet_model
            or self.anthropic_default_opus_model
            or self.anthropic_default_haiku_model
            or self.claude_model
        )

    @property
    def llm_configured(self) -> bool:
        return bool(self.anthropic_api_key or self.anthropic_auth_token)

    # --- 数据库 ---
    database_url: str = "sqlite:///./plm.db"

    # --- 认证 ---
    admin_username: str = "admin"
    admin_password: str = "admin123"
    session_secret: str = "change-me-in-production"

    # --- 定时轮询(分钟);0 = 关闭定时,仅手动「立即检查」 ---
    poll_interval_minutes: int = 0

    # --- 评审引擎 ---
    # ocr = 调用 Alibaba open-code-review 的 `ocr` CLI(默认);builtin = 内置 diff→模型 引擎
    review_engine: str = "ocr"
    ocr_bin: str = "ocr"  # ocr CLI 可执行文件路径或命令名
    ocr_timeout_minutes: int = 15  # 单个提交评审超时

    # --- 静态检查(ESLint) ---
    node_bin: str = "node"  # node 可执行文件路径或命令名(供 eslint-runner 调用)

    # --- 看板过滤 ---
    # 隐藏这些提交人的评审(逗号分隔),如 CI 机器人自动构建提交;默认隐藏 robot
    hidden_commit_authors: str = "robot"

    @property
    def hidden_authors(self) -> set[str]:
        return {a.strip() for a in self.hidden_commit_authors.split(",") if a.strip()}

    # --- CORS ---
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
