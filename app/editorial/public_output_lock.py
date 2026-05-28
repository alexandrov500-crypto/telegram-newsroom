"""Public channel output lock — no internal/debug fields on channel."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Forbidden in public Telegram channel output.
_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("quality_score", re.compile(r"\bquality\s*[:=]", re.I)),
    ("duplicates", re.compile(r"\bduplicates?\s*[:=]", re.I)),
    ("priority", re.compile(r"\bpriority\s*[:=]", re.I)),
    ("governance", re.compile(r"\bgovernance\b", re.I)),
    ("cluster", re.compile(r"\bcluster\s*(id|size|metadata)", re.I)),
    ("draft_id", re.compile(r"\bdraft\s*#?\d+", re.I)),
    ("source_reputation", re.compile(r"source\s+reputation", re.I)),
    ("category_confidence", re.compile(r"category\s+confidence", re.I)),
    ("ranking", re.compile(r"\branking\s+(trace|score)", re.I)),
    ("debug", re.compile(r"\b(debug|diagnostic)\b", re.I)),
    ("json_sources", re.compile(r"sources\s*\(json\)", re.I)),
    ("json_sources_ru", re.compile(r"источники\s*\(json\)", re.I)),
    ("pre_block", re.compile(r"<pre\b", re.I)),
    ("json_channel", re.compile(r'\{\s*"channel"\s*:', re.I)),
    ("json_array", re.compile(r'\[\s*\{\s*"channel"', re.I)),
    ("trace_id", re.compile(r"\btrace_id\s*[:=]", re.I)),
    ("wrapper_exit", re.compile(r"\bwrapper_exit\b", re.I)),
    ("pipeline_fatal", re.compile(r"\bPIPELINE_FATAL\b", re.I)),
    ("metric_line", re.compile(r"^\s*[\w.]+\s*:\s*0\.\d+\s*$", re.I | re.M)),
)


@dataclass(frozen=True)
class PublicOutputLockResult:
    ok: bool
    violations: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return not self.ok


def enforce_public_output_lock(text: str) -> PublicOutputLockResult:
    """Return violations if channel text contains internal moderation markers."""
    violations: list[str] = []
    blob = text or ""
    for name, rx in _FORBIDDEN_PATTERNS:
        if rx.search(blob):
            violations.append(name)
    return PublicOutputLockResult(ok=not violations, violations=tuple(violations))


def log_public_output_lock(
    *,
    draft_id: int | None,
    html: str,
    result: PublicOutputLockResult,
) -> None:
    """Always log lock evaluation when debug or violation (never silent)."""
    import os

    debug = os.getenv("FINAL_PUBLISH_GATE_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not debug and result.ok:
        return
    logger.info(
        "public_output_lock %s",
        json.dumps(
            {
                "draft_id": draft_id,
                "ok": result.ok,
                "violations": list(result.violations),
                "html_len": len(html or ""),
            },
            ensure_ascii=False,
        ),
    )
