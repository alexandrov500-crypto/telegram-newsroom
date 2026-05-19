from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from bot.settings import BotSettings
from bot.settings import load_settings as _load_pydantic_settings

logger = logging.getLogger(__name__)

_PRIMARY_ENV_VAR = "TELEGRAM_BOT_TOKEN"
_FALLBACK_ENV_VAR = "BOT_TOKEN"
_OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
_OPENAI_MODEL_ENV_VAR = "OPENAI_MODEL"
_DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def env_file_path() -> Path:
    return project_root() / ".env"


def bootstrap_env() -> bool:
    path = env_file_path()
    return load_dotenv(dotenv_path=path, override=True)


def get_openai_api_key() -> str | None:
    bootstrap_env()
    return os.getenv(_OPENAI_API_KEY_ENV_VAR, "").strip() or None


def get_openai_model() -> str:
    bootstrap_env()
    return os.getenv(_OPENAI_MODEL_ENV_VAR, "").strip() or _DEFAULT_OPENAI_MODEL


def get_semantic_similarity_threshold() -> float:
    return load_settings().semantic_similarity_threshold


def get_high_trust_sources() -> frozenset[str]:
    return load_settings().high_trust_source_set


def telethon_configured(settings: BotSettings) -> bool:
    return settings.telethon_configured()


def is_auto_approval_enabled() -> bool:
    bootstrap_env()
    raw = os.getenv("AUTO_APPROVAL_ENABLED", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def load_settings(env_path: Path | None = None) -> BotSettings:
    """Load settings; exit process if bot token missing (CLI entrypoints)."""
    if env_path is not None:
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        bootstrap_env()
    token = os.getenv(_PRIMARY_ENV_VAR, "").strip() or os.getenv(_FALLBACK_ENV_VAR, "").strip()
    if not token:
        print(
            f"ERROR: {_PRIMARY_ENV_VAR} (or {_FALLBACK_ENV_VAR}) is not set.\n"
            f"Expected in: {env_file_path().resolve()}",
            file=sys.stderr,
        )
        sys.exit(1)
    settings = _load_pydantic_settings()
    if settings.openai_api_key:
        logger.info("OpenAI configured model=%s", settings.openai_model)
    else:
        logger.warning("OPENAI_API_KEY not set; LLM features use deterministic fallback")
    return settings
