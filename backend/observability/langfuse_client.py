"""
QueryMind — LangFuse Observability Client
"""
from langfuse import Langfuse
from backend.core.config import settings

_langfuse: Langfuse | None = None


def init_langfuse() -> Langfuse:
    global _langfuse
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return None
    _langfuse = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
    )
    return _langfuse


def get_langfuse() -> Langfuse | None:
    return _langfuse
