"""Attention pressure buffer — cluster starvation + cooldown paralysis relief."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.osgcp.config import attention_buffer_size


class BufferMode(str, Enum):
    SYNTHESIS = "synthesis"
    CONTEXT_MERGE = "context_merge"
    SIGNAL_REPLAY = "signal_replay"


@dataclass(frozen=True)
class BufferedNarrative:
    mode: BufferMode
    selected_clusters: tuple[str, ...]
    narrative_structure: str
    combined_preview: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "selected_clusters": list(self.selected_clusters),
            "narrative_structure": self.narrative_structure,
            "combined_preview": self.combined_preview[:400],
        }


def _signal_tier(quality_score: float) -> str:
    if quality_score >= 62:
        return "high"
    if quality_score >= 48:
        return "medium"
    return "low"


def record_attention_cluster(
    runtime_dir: str | None,
    *,
    fingerprint: str,
    combined_text: str,
    quality_score: float,
    topic_hint: str = "",
) -> None:
    from app.editorial.osgcp.state import load_state, save_state

    data = load_state(runtime_dir)
    buf = list(data.get("attention_buffer") or [])
    entry = {
        "fingerprint": fingerprint,
        "text": (combined_text or "")[:3000],
        "quality_score": quality_score,
        "tier": _signal_tier(quality_score),
        "topic_hint": topic_hint,
        "ts_unix": time.time(),
    }
    buf = [b for b in buf if isinstance(b, dict) and b.get("fingerprint") != fingerprint]
    buf.append(entry)
    data["attention_buffer"] = buf[-attention_buffer_size():]
    save_state(runtime_dir, data)


def build_buffered_narrative(
    runtime_dir: str | None,
    *,
    prefer_mode: BufferMode | None = None,
) -> BufferedNarrative | None:
    from app.editorial.osgcp.state import load_state

    buf = list((load_state(runtime_dir).get("attention_buffer") or []))
    if not buf:
        return None

    high = [b for b in buf if isinstance(b, dict) and b.get("tier") == "high"]
    medium = [b for b in buf if isinstance(b, dict) and b.get("tier") == "medium"]
    pool = high or medium or [b for b in buf if isinstance(b, dict)]

    if not pool:
        return None

    pool.sort(key=lambda x: float(x.get("quality_score") or 0), reverse=True)
    selected = pool[:3]
    texts = [str(c.get("text") or "")[:500] for c in selected]

    mode = prefer_mode or (BufferMode.SIGNAL_REPLAY if high else BufferMode.CONTEXT_MERGE)
    if len(selected) >= 2 and not high:
        mode = BufferMode.SYNTHESIS

    preview = "\n".join(texts)
    structure = "Event → Context → Implication → Takeaway"

    return BufferedNarrative(
        mode=mode,
        selected_clusters=tuple(str(c.get("fingerprint") or "") for c in selected),
        narrative_structure=structure,
        combined_preview=preview,
    )
