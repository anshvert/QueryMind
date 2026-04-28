"""
QueryMind — Application Configuration
Loaded from environment variables via pydantic-settings
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    # --- PostgreSQL ---
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "querymind"
    POSTGRES_USER: str = "querymind"
    POSTGRES_PASSWORD: str = "querymind_secret"
    DATABASE_URL: str = "postgresql+asyncpg://querymind:querymind_secret@localhost:5432/querymind"
    DATABASE_URL_SYNC: str = "postgresql://querymind:querymind_secret@localhost:5432/querymind"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""

    # --- Qdrant ---
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_SCHEMA: str = "schema_embeddings"
    QDRANT_COLLECTION_MEMORY: str = "user_memory"
    QDRANT_COLLECTION_QUERY_CACHE: str = "query_cache"

    # --- OpenRouter (LLM) ---
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_SQL_MODEL: str = "anthropic/claude-sonnet-4-5"
    LLM_FAST_MODEL: str = "openai/gpt-4o-mini"
    LLM_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

    # --- LangFuse ---
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # --- Encryption ---
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # --- CORS ---
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Auth ---
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Snowflake ---
    SNOWFLAKE_ACCOUNT: str = ""
    SNOWFLAKE_USER: str = ""
    SNOWFLAKE_PASSWORD: str = ""
    SNOWFLAKE_WAREHOUSE: str = ""
    SNOWFLAKE_DATABASE: str = ""
    SNOWFLAKE_SCHEMA: str = ""

    # --- BigQuery ---
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    BIGQUERY_PROJECT_ID: str = ""

    # --- vLLM ---
    VLLM_BASE_URL: str = "http://localhost:8001/v1"
    VLLM_MODEL: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    VLLM_EMBEDDING_SIMILARITY_THRESHOLD: float = 0.95

    # --- Security / Query Guardrails ---
    MAX_QUERY_ROWS: int = 10000
    QUERY_TIMEOUT_SECONDS: int = 30
    ENABLE_PII_MASKING: bool = True
    ENABLE_AUDIT_LOGS: bool = True
    RBAC_ENABLED: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
