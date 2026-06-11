"""Attention Design System — Hook / Meaning / Implication layers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_MEANING = re.compile(
    r"(значит|означает|важн|matters|потому\s+что|это\s+говорит|сигнал|риск|влияет)",
    re.I,
)
_IMPLICATION = re.compile(
    r"(дальше|следующ|expect|ожида|изменит|will|может\s+привести|последств)",
    re.I,
)
_JUST_REPORTING = re.compile(
    r"^(?:по\s+данным|сообщает|источник\s+сообщил|according\s+to)\s",
    re.I,
)


@dataclass(frozen=True)
class AttentionDesign:
    has_hook: bool
    has_meaning: bool
    has_implication: bool
    just_reporting: bool
    passes: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_hook": self.has_hook,
            "has_meaning": self.has_meaning,
            "has_implication": self.has_implication,
            "just_reporting": self.just_reporting,
            "passes": self.passes,
            "reason": self.reason,
        }


def evaluate_attention_design(text: str, *, post_type: str = "") -> AttentionDesign:
    t = (text or "").strip()
    if not t:
        return AttentionDesign(False, False, False, True, False, "empty")

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    hook_line = lines[0] if lines else ""
    has_hook = len(hook_line) >= 20 and not _JUST_REPORTING.search(hook_line)
    has_meaning = bool(_MEANING.search(t))
    has_implication = bool(_IMPLICATION.search(t))
    just_reporting = bool(_JUST_REPORTING.match(t)) and not has_meaning

    pt = (post_type or "").lower()
    if pt in {"digest", "explainer", "context"}:
        passes = has_hook or has_meaning
        reason = "digest_exempt" if passes else "digest_missing_structure"
    else:
        passes = has_hook and has_meaning and not just_reporting
        reason = "ok" if passes else "missing_attention_layers"

    return AttentionDesign(
        has_hook=has_hook,
        has_meaning=has_meaning,
        has_implication=has_implication,
        just_reporting=just_reporting,
        passes=passes,
        reason=reason,
    )


def enrich_attention_layers(text: str, *, post_type: str = "") -> str:
    """Light-touch enrichment when layers are weak but content is not empty."""
    try:
        from app.editorial.clean_channel_copy import clean_channel_copy_enabled

        if clean_channel_copy_enabled():
            return (text or "").strip()
    except Exception:
        pass
    design = evaluate_attention_design(text, post_type=post_type)
    if design.passes or not (text or "").strip():
        return text
    out = text.strip()
    if not design.has_meaning and post_type not in {"digest"}:
        out += "\n\nПочему это важно: событие меняет контекст для рынков и решений."
    if not design.has_implication:
        out += "\n\nЧто дальше: следим за подтверждением и реакцией участников."
    return out.strip()
