"""
全局配置模块：仅从环境变量读取，密钥不进镜像。
部署时由运维通过环境变量注入；本地开发可使用 .env 文件（不提交到仓库）。
v7: 新增 Claude、test_mode 等。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
from pathlib import Path

# Application Version
APP_VERSION = "4.0.0"
API_VERSION = "v1"


class Settings(BaseSettings):
    """应用配置类 - 全部环境变量"""

    # OpenAI API (v1.2 §3.1: 规划官 + 物理裁判)
    openai_api_key: str = Field(..., description="OpenAI API Key")
    openai_api_base: Optional[str] = Field(default=None, description="OpenAI API Base URL (proxy)")
    openai_model: str = Field(default="gpt-4o", description="OpenAI Model")
    openai_max_tokens: int = Field(default=4096, description="Max tokens")
    openai_temperature: float = Field(default=0.7, description="Temperature")

    # Google Gemini API (v1.2 §3.1: 知识补充 + 文献审计)
    gemini_api_key: str = Field(..., description="Google Gemini API Key")
    gemini_api_base: Optional[str] = Field(default=None, description="Gemini API Base URL (proxy)")
    gemini_model: str = Field(default="gemini-2.0-flash-exp", description="Gemini Model")

    # v7.1: Claude API (v1.2 §3.1: 主程序员 + 执行引擎)
    claude_api_key: Optional[str] = Field(default=None, description="Anthropic Claude API Key")
    claude_api_base: Optional[str] = Field(default=None, description="Claude API Base URL (proxy)")
    claude_model: str = Field(default="claude-opus-4-20250514", description="Claude Model")

    # App
    app_env: str = Field(default="development", description="development | production")
    app_host: str = Field(default="0.0.0.0", description="Bind host")
    app_port: int = Field(default=8000, description="Bind port")
    debug: bool = Field(default=True, description="Debug mode")

    # 数据目录（部署时挂载为 volume：chroma + files）
    vector_db_path: str = Field(default="./data/chroma", description="ChromaDB 数据目录")
    projects_path: str = Field(default="./data/files", description="业务文件 JSON/MD 目录")

    # 数据库：生产用 PostgreSQL，由 DATABASE_URL 指定；不设则退回到 SQLite（仅开发）
    database_url: Optional[str] = Field(default=None, description="PostgreSQL: postgresql://user:pass@host/db。不设则用 SQLite")

    # 认证
    secret_key: str = Field(default="dev-only-set-SECRET_KEY-in-production", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=15, description="Access token 过期分钟")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token 过期天数")

    # CORS：前后端不同域时，前端域名列表，逗号分隔
    cors_origins: str = Field(default="http://localhost:5173", description="允许的源，逗号分隔")

    # v7: 测试模式 - 跳过前置与 gate 检查（仅管理员可切换）
    test_mode: bool = Field(default=False, description="Test mode: skip prerequisite and gate checks")

    # Retry / Logging
    max_retries: int = Field(default=3, description="API 重试次数")
    retry_delay: int = Field(default=2, description="重试间隔秒")
    api_timeout: int = Field(default=300, description="API 超时秒")
    step_interval_delay: int = Field(default=5, description="步骤间隔秒")
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: str = Field(default="./logs/app.log", description="日志文件路径")

    # v4.0
    agentic_wrapper_enabled: bool = Field(default=True, description="Agentic Wrapper")
    gemini_gem_config_path: Optional[str] = Field(default=None, description="Gemini Gem 配置路径")
    doi_validation_enabled: bool = Field(default=True, description="DOI 校验")
    doi_cache_ttl: int = Field(default=86400, description="DOI 缓存 TTL 秒")
    doi_api_timeout: int = Field(default=10, description="DOI API 超时秒")
    consistency_check_enabled: bool = Field(default=True, description="一致性检查")
    consistency_check_threshold: float = Field(default=0.8, description="一致性阈值 0-1")

    # 工作流 YAML 目录
    workflows_dir: str = Field(default="./workflows", description="工作流 YAML 文件目录")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        Path(self.vector_db_path).mkdir(parents=True, exist_ok=True)
        Path(self.projects_path).mkdir(parents=True, exist_ok=True)
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    def get_cors_origins_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()

OPENAI_API_KEY = settings.openai_api_key
OPENAI_MODEL = settings.openai_model
GEMINI_API_KEY = settings.gemini_api_key
GEMINI_MODEL = settings.gemini_model
VECTOR_DB_PATH = settings.vector_db_path
PROJECTS_PATH = settings.projects_path
MAX_RETRIES = settings.max_retries
RETRY_DELAY = settings.retry_delay
