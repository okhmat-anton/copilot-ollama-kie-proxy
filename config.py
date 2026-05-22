"""Конфигурация приложения. Читает переменные из .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    # KIE.AI
    kie_ai_api_key: str = field(
        default_factory=lambda: os.getenv("KIE_AI_API_KEY", "")
    )
    kie_ai_api_url: str = field(
        default_factory=lambda: os.getenv("KIE_AI_API_URL", "https://api.kie.ai/v1").rstrip("/")
    )

    # Proxy
    proxy_host: str = field(default_factory=lambda: os.getenv("PROXY_HOST", "127.0.0.1"))
    proxy_port: int = field(default_factory=lambda: _env_int("PROXY_PORT", 11777))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    log_dir: Path = field(default_factory=lambda: Path(os.getenv("LOG_DIR", "./logs")))
    request_logging_enabled: bool = field(
        default_factory=lambda: _env_bool("REQUEST_LOGGING_ENABLED", True)
    )
    request_log_headers: bool = field(
        default_factory=lambda: _env_bool("REQUEST_LOG_HEADERS", True)
    )
    request_log_body: bool = field(
        default_factory=lambda: _env_bool("REQUEST_LOG_BODY", True)
    )
    request_log_body_limit: int = field(
        default_factory=lambda: _env_int("REQUEST_LOG_BODY_LIMIT", 4096)
    )

    # Models
    default_model: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
    )
    available_models: List[str] = field(
        default_factory=lambda: _env_list(
            "AVAILABLE_MODELS",
            ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
        )
    )
    ollama_compat_version: str = field(
        default_factory=lambda: os.getenv("OLLAMA_COMPAT_VERSION", "0.8.0")
    )
    model_context_length: int = field(
        default_factory=lambda: _env_int("MODEL_CONTEXT_LENGTH", 1_000_000)
    )

    # HTTP client
    upstream_timeout: float = field(
        default_factory=lambda: float(os.getenv("UPSTREAM_TIMEOUT", "120"))
    )

    # Dev mode: дублирует все логгеры в stderr и включает подробные DEBUG-логи
    dev_mode: bool = field(default_factory=lambda: _env_bool("DEV_MODE", False))

    def __post_init__(self) -> None:
        if self.default_model not in self.available_models:
            self.available_models.insert(0, self.default_model)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
