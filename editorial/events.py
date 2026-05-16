"""Event fingerprints, rolling history, update-vs-new heuristics (deterministic)."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from typing import Any

from db.models import RawPost

from editorial.event_models import EventCluster, EventEvolution, EventIdentity
from editorial.intelligence_store import event_history_path, load_json, save_json


def _norm_channel(ch: str) -> str:
    return str(ch or "").strip().lower()


def _topic_hint_from_posts(posts: list[RawPost]) -> str:
    words: list[str] = []
    for p in posts[:6]:
        for w in re.findall(r"[\w\-\u0400-\u04FF]{5,}", (p.text or "").lower()):
            words.append(w)
    if not words:
        return "unknown"
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
    return " ".join(t[0] for t in top) or "unknown"


def compute_event_fingerprint(posts: list[RawPost]) -> str:
    """Lexical + channel + id multiset fingerprint (stable ordering)."""
    parts: list[str] = []
    for p in sorted(posts, key=lambda x: (x.id,)):
        parts.append(f"{p.id}:{_norm_channel(p.channel_name)}:{hashlib.sha256((p.text or '').encode('utf-8', errors='ignore')).hexdigest()[:16]}")
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_event_cluster(posts: list[RawPost], *, cohesion: float) -> EventCluster:
    fp = compute_event_fingerprint(posts)
    return EventCluster(fingerprint=fp, post_ids=tuple(p.id for p in posts), size=len(posts), cohesion=round(cohesion, 4))


def _jaccard_words(a: str, b: str) -> float:
    wa = {x for x in re.findall(r"[\w\-\u0400-\u04FF]{4,}", a.lower()) if len(x) >= 4}
    wb = {x for x in re.findall(r"[\w\-\u0400-\u04FF]{4,}", b.lower()) if len(x) >= 4}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, len(wa | wb))


def classify_event_evolution(
    current_fp: str,
    *,
    combined_text: str,
    history: list[dict[str, Any]],
    max_compare: int = 24,
) -> EventEvolution:
    """
    Heuristic: high lexical overlap with a recent event fingerprint row → ``update``;
    same fingerprint seen before → ``update``; else ``new``.
    """
    reasons: list[str] = []
    best_fp: str | None = None
    best_sim = 0.0
    for row in history[:max_compare]:
        prev_fp = str(row.get("fingerprint") or "")
        prev_text = str(row.get("combined_text_excerpt") or "")
        if not prev_fp:
            continue
        if prev_fp == current_fp:
            reasons.append("exact_fingerprint_match")
            return EventEvolution("update", 1.0, prev_fp, tuple(reasons))
        sim = _jaccard_words(combined_text, prev_text)
        if sim > best_sim:
            best_sim = sim
            best_fp = prev_fp
    continuity = round(max(0.0, min(1.0, best_sim)), 4)
    if best_sim >= 0.55:
        reasons.append("high_lexical_overlap_with_recent")
        return EventEvolution("update", continuity, best_fp, tuple(reasons))
    if best_sim >= 0.28:
        reasons.append("partial_overlap")
        return EventEvolution("ambiguous", continuity, best_fp, tuple(reasons))
    reasons.append("no_strong_match")
    return EventEvolution("new", continuity, None, tuple(reasons))


def event_freshness_decay(last_seen_unix: float, *, now_unix: float | None = None) -> float:
    """1.0 = just seen, decays exponentially with ~36h half-life."""
    now = float(now_unix or time.time())
    age_h = max(0.0, (now - float(last_seen_unix)) / 3600.0)
    return round(math.exp(-age_h / 36.0), 4)


def append_event_history(
    runtime_dir: str | None,
    *,
    fingerprint: str,
    combined_text_excerpt: str,
    max_entries: int = 120,
) -> None:
    path = event_history_path(runtime_dir)
    data = load_json(path, {"version": 1, "events": []})
    events = list(data.get("events") or [])
    events.insert(
        0,
        {
            "fingerprint": fingerprint,
            "combined_text_excerpt": combined_text_excerpt[:4000],
            "ts": time.time(),
        },
    )
    data["events"] = events[:max_entries]
    save_json(path, data)


def load_event_history(runtime_dir: str | None, *, limit: int = 80) -> list[dict[str, Any]]:
    data = load_json(event_history_path(runtime_dir), {"version": 1, "events": []})
    ev = data.get("events")
    if not isinstance(ev, list):
        return []
    return [x for x in ev if isinstance(x, dict)][:limit]


def compact_event_history(
    runtime_dir: str | None,
    *,
    max_entries: int = 120,
    max_age_sec: float | None = None,
) -> dict[str, Any]:
    """Trim rolling event history by age and entry cap (newest-first list)."""
    path = event_history_path(runtime_dir)
    data = load_json(path, {"version": 1, "events": []})
    events = [x for x in (data.get("events") or []) if isinstance(x, dict)]
    now = time.time()
    if max_age_sec is not None:
        ma = float(max_age_sec)
        events = [e for e in events if now - float(e.get("ts") or 0.0) <= ma]
    before = len(events)
    events = events[: max(1, min(int(max_entries), 500))]
    data["events"] = events
    save_json(path, data)
    return {"path": str(path), "before": before, "kept": len(events)}


def build_event_identity(posts: list[RawPost], *, now_unix: float | None = None) -> EventIdentity:
    ts = float(now_unix or time.time())
    fp = compute_event_fingerprint(posts)
    chans = tuple(sorted({_norm_channel(p.channel_name) for p in posts if _norm_channel(p.channel_name)}))
    hint = _topic_hint_from_posts(posts)
    return EventIdentity(fingerprint=fp, topic_hint=hint, channel_keys=chans, first_seen_unix=ts, last_seen_unix=ts)
