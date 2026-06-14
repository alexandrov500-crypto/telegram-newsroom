"""Declarative editorial governance rules (reloadable, observable)."""

from __future__ import annotations

import os
import time
from typing import Any

from db.models import RawPost

from editorial.governance.paths import governance_rules_path
from editorial.governance.reputation import explainable_reputation
from editorial.intelligence_store import load_json, save_json
from editorial.suppression_memory import duplicate_burst_count, is_suppression_active

DEFAULT_RULES: dict[str, Any] = {
    "version": 1,
    "rules": [
        {
            "id": "suppress_repeated_topics",
            "enabled": True,
            "type": "topic_repeat_cooldown",
            "min_interval_sec": 1800,
            "description": "Defer clusters on topics recently selected",
        },
        {
            "id": "block_low_trust_sources",
            "enabled": True,
            "type": "min_source_trust",
            "threshold": 0.35,
            "description": "Suppress when dominant source trust is below threshold",
        },
        {
            "id": "minimum_source_diversity",
            "enabled": True,
            "type": "min_unique_channels",
            "min_channels": 1,
            "min_ratio": 0.1,
            "description": "Require minimum channel spread in multi-post clusters",
        },
        {
            "id": "geopolitical_throttle",
            "enabled": True,
            "type": "keyword_throttle",
            "keywords": ["war", "nato", "sanctions", "missile", "invasion"],
            "max_per_hour": 4,
            "description": "Limit high-volume geopolitical clusters per hour",
        },
        {
            "id": "crisis_burst_throttle",
            "enabled": True,
            "type": "duplicate_burst",
            "burst_threshold": 8,
            "description": "Throttle when duplicate burst counter exceeds threshold",
        },
        {
            "id": "anti_spam_burst",
            "enabled": True,
            "type": "cluster_size_cap",
            "max_posts": 40,
            "description": "Suppress oversized single-channel bursts",
        },
    ],
}


def load_governance_rules(runtime_dir: str | None) -> dict[str, Any]:
    data = load_json(governance_rules_path(runtime_dir), DEFAULT_RULES)
    if not data.get("rules"):
        data["rules"] = list(DEFAULT_RULES["rules"])
    return data


def reload_governance_rules(runtime_dir: str | None) -> dict[str, Any]:
    return load_governance_rules(runtime_dir)


def _state(runtime_dir: str | None) -> dict[str, Any]:
    from editorial.governance.paths import governance_state_path

    return load_json(
        governance_state_path(runtime_dir),
        {"version": 1, "topic_last_selected": {}, "geo_hour": {}},
    )


def _save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    from editorial.governance.paths import governance_state_path

    save_json(governance_state_path(runtime_dir), data)


def evaluate_policies(
    posts: list[RawPost],
    *,
    runtime_dir: str | None,
    topic_key: str,
    dominant_channel: str,
    fingerprint: str = "",
) -> tuple[list[dict[str, Any]], bool, str]:
    """Return (matches, should_suppress, primary_reason)."""
    rules = load_governance_rules(runtime_dir)
    matches: list[dict[str, Any]] = []
    suppress = False
    reason = ""
    rep = explainable_reputation(runtime_dir)
    state = _state(runtime_dir)
    now = time.time()
    topic_k = str(topic_key or "").strip().lower()[:80]
    dom = str(dominant_channel or "").strip().lower()
    n = len(posts)
    chans = {str(p.channel_name or "").strip().lower() for p in posts if str(p.channel_name or "").strip()}
    uniq = len(chans)

    starvation = False
    try:
        from app.editorial.desk_starvation import desk_threshold_context

        starvation = desk_threshold_context().publish_starvation_detected
    except Exception:
        pass

    for rule in rules.get("rules") or []:
        if not isinstance(rule, dict) or not rule.get("enabled", True):
            continue
        rid = str(rule.get("id") or "")
        rtype = str(rule.get("type") or "")
        if starvation and rtype == "topic_repeat_cooldown":
            continue
        hit = False
        detail: dict[str, Any] = {}

        if rtype == "topic_repeat_cooldown" and topic_k:
            last = float((state.get("topic_last_selected") or {}).get(topic_k) or 0)
            interval = float(rule.get("min_interval_sec") or 1800)
            try:
                from app.editorial.news_channel_beat import news_beat_topic_cooldown_sec

                interval = news_beat_topic_cooldown_sec(default=interval)
            except Exception:
                pass
            if last and now - last < interval:
                hit = True
                detail = {"topic": topic_k, "seconds_since": round(now - last, 1)}
        elif rtype == "min_source_trust" and dom:
            score = float(rep.get(dom, {}).get("score") or 0.5)
            thr = float(rule.get("threshold") or 0.35)
            try:
                from app.editorial.desk_starvation import desk_threshold_context

                if desk_threshold_context().publish_starvation_detected:
                    thr = min(thr, float(os.getenv("GOVERNANCE_STARVATION_TRUST_FLOOR", "0.28")))
            except Exception:
                pass
            if score < thr:
                hit = True
                detail = {"channel": dom, "score": score, "threshold": thr}
        elif rtype == "min_unique_channels" and n >= 3:
            ratio = uniq / n
            if uniq < int(rule.get("min_channels") or 1) or ratio < float(rule.get("min_ratio") or 0.25):
                hit = True
                detail = {"unique_channels": uniq, "ratio": round(ratio, 4)}
        elif rtype == "keyword_throttle":
            hay = " ".join((p.text or "")[:500] for p in posts).lower()
            kws = [str(k).lower() for k in (rule.get("keywords") or [])]
            if any(k in hay for k in kws):
                hour_key = time.strftime("%Y%m%d%H", time.gmtime())
                geo = dict(state.get("geo_hour") or {})
                cnt = int(geo.get(hour_key) or 0)
                if cnt >= int(rule.get("max_per_hour") or 4):
                    hit = True
                    detail = {"hour_key": hour_key, "count": cnt}
        elif rtype == "duplicate_burst":
            cnt = duplicate_burst_count(runtime_dir)
            if cnt >= int(rule.get("burst_threshold") or 8):
                hit = True
                detail = {"burst_count": cnt}
        elif rtype == "cluster_size_cap" and n > int(rule.get("max_posts") or 40):
            hit = True
            detail = {"cluster_size": n}
        elif rtype == "suppression_memory_key" and fingerprint:
            _skip_suppression = False
            try:
                from app.editorial.wire_recovery import wire_bypass_suppression_memory

                _skip_suppression = wire_bypass_suppression_memory()
            except Exception:
                pass
            if not _skip_suppression and is_suppression_active(runtime_dir, fingerprint):
                hit = True
                detail = {"fingerprint": fingerprint}

        if hit:
            matches.append({"rule_id": rid, "type": rtype, "detail": detail})
            if not suppress and rtype not in ("topic_repeat_cooldown",):
                suppress = True
                reason = rid
            elif rtype == "topic_repeat_cooldown":
                suppress = True
                reason = rid or "topic_repeat_cooldown"

    return matches, suppress, reason


def record_topic_selected(runtime_dir: str | None, topic_key: str) -> None:
    state = _state(runtime_dir)
    tl = dict(state.get("topic_last_selected") or {})
    tl[str(topic_key or "").strip().lower()[:80]] = time.time()
    state["topic_last_selected"] = tl
    hour_key = time.strftime("%Y%m%d%H", time.gmtime())
    geo = dict(state.get("geo_hour") or {})
    geo[hour_key] = int(geo.get(hour_key) or 0) + 1
    state["geo_hour"] = geo
    _save_state(runtime_dir, state)


def policies_payload(runtime_dir: str | None) -> dict[str, Any]:
    data = load_governance_rules(runtime_dir)
    return {
        "version": data.get("version", 1),
        "rules": data.get("rules") or [],
        "path": str(governance_rules_path(runtime_dir)),
        "reloadable": True,
    }
