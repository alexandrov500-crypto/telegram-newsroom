"""Topic fatigue and narrative saturation suppression."""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ENTITY = re.compile(
    r"\b(Fed|ECB|BTC|ETH|Bitcoin|Putin|Trump|OPEC|Apple|Tesla|"
    r"ЦБ|ФРС|нефть|Путин|санкци|ставк)\b",
    re.I,
)


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "topic_fatigue_state.json"


def _decay_hours() -> float:
    try:
        return max(4.0, float(os.getenv("GROWTH_FATIGUE_DECAY_HOURS", "18")))
    except ValueError:
        return 18.0


def _saturation_limit() -> float:
    try:
        return max(0.3, min(1.0, float(os.getenv("GROWTH_TOPIC_SATURATION_LIMIT", "0.72"))))
    except ValueError:
        return 0.72


@dataclass(frozen=True)
class FatigueVerdict:
    suppress: bool
    fatigue_score: float
    reason: str
    novelty: float


def _load(runtime_dir: str) -> dict[str, Any]:
    try:
        return json.loads(_state_path(runtime_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"topics": {}, "entities": {}, "narratives": {}}


def _save(runtime_dir: str, state: dict[str, Any]) -> None:
    p = _state_path(runtime_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")


def _decay_bucket(bucket: dict[str, Any], now: float) -> dict[str, Any]:
    out: dict[str, Any] = {}
    half_life = _decay_hours() * 3600.0
    for k, v in bucket.items():
        if not isinstance(v, dict):
            continue
        last = float(v.get("last_ts") or 0)
        count = float(v.get("count") or 0)
        if now - last > half_life * 3:
            continue
        decay = math.exp(-(now - last) / half_life) if last else 1.0
        out[k] = {"count": count * decay, "last_ts": last}
    return out


def evaluate_topic_fatigue(
    *,
    runtime_dir: str,
    topic_key: str,
    content: str,
    narrative_id: str = "",
    is_breaking: bool = False,
) -> FatigueVerdict:
    if is_breaking:
        return FatigueVerdict(False, 0.0, "breaking_exempt", 1.0)

    now = time.time()
    state = _load(runtime_dir)
    topics = _decay_bucket(dict(state.get("topics") or {}), now)
    entities = _decay_bucket(dict(state.get("entities") or {}), now)
    narratives = _decay_bucket(dict(state.get("narratives") or {}), now)

    tk = (topic_key or "general")[:64]
    topic_count = float((topics.get(tk) or {}).get("count") or 0)
    ent_hits = 0.0
    for m in _ENTITY.findall(content or ""):
        key = m.lower()
        ent_hits += float((entities.get(key) or {}).get("count") or 0)
    narr_count = float((narratives.get(narrative_id) or {}).get("count") or 0) if narrative_id else 0.0

    fatigue = min(1.0, 0.35 * topic_count + 0.08 * ent_hits + 0.25 * narr_count)
    novelty = round(max(0.0, 1.0 - fatigue), 4)

    if fatigue >= _saturation_limit():
        return FatigueVerdict(True, round(fatigue, 4), "topic_saturated", novelty)
    if ent_hits >= 4.0:
        return FatigueVerdict(True, round(fatigue, 4), "entity_overuse", novelty)
    return FatigueVerdict(False, round(fatigue, 4), "ok", novelty)


def record_topic_publish(
    *,
    runtime_dir: str,
    topic_key: str,
    content: str,
    narrative_id: str = "",
) -> None:
    now = time.time()
    state = _load(runtime_dir)

    def bump(bucket_name: str, key: str) -> None:
        if not key:
            return
        bucket: dict[str, Any] = dict(state.get(bucket_name) or {})
        row = dict(bucket.get(key) or {"count": 0.0, "last_ts": now})
        row["count"] = float(row.get("count") or 0) + 1.0
        row["last_ts"] = now
        bucket[key] = row
        state[bucket_name] = bucket

    bump("topics", (topic_key or "general")[:64])
    if narrative_id:
        bump("narratives", narrative_id[:48])
    for m in set(_ENTITY.findall(content or "")):
        bump("entities", m.lower())

    _save(runtime_dir, state)
