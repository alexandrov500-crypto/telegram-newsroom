"""Strict public-channel leak detection before Telegram send."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("debug_trace", re.compile(r"\b(traceback|stack\s*trace|file\s+\"[^\"]+\",\s+line\s+\d+)\b", re.I)),
    ("quality_block", re.compile(r"\bquality\s+block\b|\bQuality\s*block\b", re.I)),
    ("governance_leak", re.compile(r"\bgovernance\b|\bauto_block\b|\bmanual_review\b", re.I)),
    ("internal_scores", re.compile(r"\b(trust_score|signal_score|priority_score|editorial_score)\s*[:=]", re.I)),
    ("pipeline_terms", re.compile(r"\b(PIPELINE_|wrapper_|trace_id|pipeline_decision|execution_registry)\b", re.I)),
    ("moderation_reason", re.compile(r"\b(moderation_reason|reject_reason|desk\.reject|reason_code)\s*[:=]", re.I)),
    ("raw_metrics", re.compile(r"^\s*[\w.]+\s*:\s*(0\.\d+|\d+%)\s*$", re.I | re.M)),
    ("cluster_internal", re.compile(r"\bcluster\s*(id|metadata|intelligence)\b", re.I)),
    ("draft_internal", re.compile(r"\bdraft\s*#?\d+\b.*\b(status|extras)\b", re.I)),
    ("json_sources_ru", re.compile(r"источники\s*\(json\)", re.I)),
    ("json_sources_en", re.compile(r"sources\s*\(json\)", re.I)),
    ("json_channel", re.compile(r'\{\s*"channel"\s*:', re.I)),
    ("json_array", re.compile(r'\[\s*\{\s*"channel"', re.I)),
    ("pre_block", re.compile(r"<pre\b", re.I)),
    ("empty_placeholder", re.compile(r"\(\s*empty\s*\)|\.\.\.\s*empty\s*\)", re.I)),
    ("pipeline_fatal", re.compile(r"\bPIPELINE_FATAL\b", re.I)),
)


@dataclass(frozen=True)
class PublicContentSanitizerResult:
    ok: bool
    violations: tuple[str, ...]
    strict: bool

    @property
    def blocked(self) -> bool:
        return not self.ok


def public_content_sanitizer_strict(settings: Settings | None) -> bool:
    if settings is not None:
        return bool(getattr(settings, "public_content_sanitizer_strict", False))
    import os

    return os.getenv("PUBLIC_CONTENT_SANITIZER_STRICT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def evaluate_public_content_sanitizer(
    text: str,
    *,
    settings: Settings | None = None,
    strict: bool | None = None,
) -> PublicContentSanitizerResult:
    """Scan channel HTML/plain for internal editorial / pipeline leaks."""
    use_strict = public_content_sanitizer_strict(settings) if strict is None else bool(strict)
    blob = text or ""
    violations: list[str] = []
    for name, rx in _LEAK_PATTERNS:
        if rx.search(blob):
            violations.append(name)
    ok = not violations if use_strict else True
    return PublicContentSanitizerResult(ok=ok, violations=tuple(violations), strict=use_strict)


def log_public_content_leak_blocked(
    *,
    draft_id: int | None,
    result: PublicContentSanitizerResult,
    html_len: int = 0,
) -> None:
    if result.ok:
        return
    payload: dict[str, Any] = {
        "event": "PUBLIC_CONTENT_LEAK_BLOCKED",
        "draft_id": draft_id,
        "violations": list(result.violations),
        "strict": result.strict,
        "html_len": html_len,
    }
    logger.warning("%s", json.dumps(payload, ensure_ascii=False))
