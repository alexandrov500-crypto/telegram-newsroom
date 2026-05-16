from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass
from typing import Any

try:
    import sqlalchemy.exc as sa_exc  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    sa_exc = None  # type: ignore[assignment]

try:
    from openai import APIError, APITimeoutError  # type: ignore[import-not-found]
except Exception:  # pragma: no cover

    class APIError(Exception):
        pass

    class APITimeoutError(Exception):
        pass


_CODE_SANITIZE = re.compile(r"[^a-z0-9_.]+", re.I)


@dataclass(frozen=True, slots=True)
class ClassifiedError:
    category: str
    severity: str
    retryable: bool
    code: str


def _norm_code(s: str) -> str:
    s = s.strip().lower().replace(" ", "_")
    s = _CODE_SANITIZE.sub("_", s)
    return s[:80] or "unknown"


def _walk_chain(exc: BaseException) -> list[BaseException]:
    out: list[BaseException] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        out.append(cur)
        cur = cur.__cause__ or cur.__context__
    return out


def pick(cat: str, sev: str, retry: bool, code: str) -> ClassifiedError:
    return ClassifiedError(category=cat, severity=sev, retryable=retry, code=_norm_code(code))


def classify_runtime_error(exc: BaseException) -> ClassifiedError:
    """
    Best-effort classification for logging / dumps (no I/O).
    Categories: database, network, openai, telegram, scheduler, validation, unknown.
    """
    if sys.version_info >= (3, 11) and isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            c = classify_runtime_error(sub)
            if c.category != "unknown":
                return c
        if exc.exceptions:
            return classify_runtime_error(exc.exceptions[0])
        return pick("unknown", "medium", False, "unknown.empty_exception_group")

    chain = _walk_chain(exc)
    types = [type(e).__name__ for e in chain]
    mod_names = [type(e).__module__ for e in chain]
    msgs = " ".join(str(e) for e in chain).lower()

    # OpenAI (typed first)
    for e in chain:
        if isinstance(e, (APIError, APITimeoutError)):
            return pick("openai", "medium", True, f"openai.{type(e).__name__}")
    if "rate limit" in msgs and ("openai" in msgs or "token" in msgs):
        return pick("openai", "medium", True, "openai.rate_limit_heuristic")

    # SQLAlchemy / DBAPI
    if sa_exc is not None:
        for e in chain:
            if isinstance(e, sa_exc.SQLAlchemyError):
                retry = isinstance(
                    e,
                    (
                        sa_exc.OperationalError,
                        sa_exc.TimeoutError,
                        sa_exc.DisconnectionError,
                    ),
                )
                return pick("database", "high", retry, f"database.{type(e).__name__}")

    for e in chain:
        tn = type(e).__name__.lower()
        if "sqlite" in tn or "asyncpg" in tn or "psycopg" in tn:
            retry = "operational" in tn or "busy" in msgs or "timeout" in msgs
            return pick("database", "high", retry, f"database.{type(e).__name__}")

    # Telegram / Telethon
    for mod, tn in zip(mod_names, types):
        if "telethon" in mod or "telegram" in mod or "telethon" in tn.lower():
            return pick("telegram", "medium", True, f"telegram.{tn}")

    for e in chain:
        if isinstance(e, ConnectionError):
            return pick("network", "medium", True, f"network.{type(e).__name__}")
    for e in chain:
        if isinstance(e, OSError) and getattr(e, "errno", None) not in (None, 0):
            return pick("network", "medium", True, f"network.errno_{e.errno}")

    # Scheduler / asyncio
    for e in chain:
        if isinstance(e, asyncio.CancelledError):
            return pick("scheduler", "low", False, "scheduler.cancelled")
    for e in chain:
        if isinstance(e, asyncio.TimeoutError):
            return pick("scheduler", "medium", True, "scheduler.asyncio_timeout")

    # Validation-style
    for e in chain:
        if isinstance(e, (ValueError, TypeError)):
            return pick("validation", "low", False, f"validation.{type(e).__name__}")
    for e in chain:
        if isinstance(e, RuntimeError) and any(
            x in str(e).lower() for x in ("startup validation", "required", "invalid", "must be")
        ):
            return pick("validation", "medium", False, "validation.runtime_config")

    # OpenAI heuristic (untyped)
    if "openai" in msgs:
        return pick("openai", "medium", True, "openai.message_heuristic")

    root = chain[0]
    return pick("unknown", "medium", False, f"unknown.{type(root).__name__}")
