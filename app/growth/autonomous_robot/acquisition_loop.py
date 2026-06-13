"""Phase 4 — acquisition loop: pin candidates, bio hints, share-nudge tuning."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from db.models import Draft, PostPerformance
from db.session import session_scope


def acquisition_loop_enabled() -> bool:
    return os.getenv("AUTONOMOUS_ACQUISITION_LOOP_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "autonomous_acquisition_state.json"


def _load_state(runtime_dir: str) -> dict[str, Any]:
    path = _state_path(runtime_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(runtime_dir: str, state: dict[str, Any]) -> None:
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _bio_templates() -> list[str]:
    raw = os.getenv(
        "ACQUISITION_BIO_TEMPLATES",
        "Макро и рынки без воды — коротко и вовремя|Экономика и финансы: wire-speed новости|Главный канал по макро — подпишитесь",
    )
    return [t.strip() for t in raw.split("|") if t.strip()]


async def _top_forward_posts(*, channel_id: int | None, limit: int = 5) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=7)
    async with session_scope() as session:
        q = (
            select(PostPerformance, Draft.content)
            .join(Draft, Draft.id == PostPerformance.draft_id, isouter=True)
            .where(PostPerformance.published_at >= cutoff)
            .where(PostPerformance.snapshot_label == "t24h")
            .order_by(PostPerformance.forwards.desc(), PostPerformance.views.desc())
            .limit(40)
        )
        if channel_id:
            q = q.where(PostPerformance.channel_id == int(channel_id))
        rows = list((await session.execute(q)).all())

    ranked: list[tuple[float, PostPerformance, str]] = []
    for perf, content in rows:
        views = float(getattr(perf, "views", 0) or 1)
        forwards = float(getattr(perf, "forwards", 0) or 0)
        rate = forwards / max(1.0, views)
        ranked.append((rate, perf, str(content or "")))

    ranked.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for rate, row, content in ranked[:limit]:
        snippet = content.strip().replace("\n", " ")[:120]
        out.append(
            {
                "draft_id": int(row.draft_id or 0),
                "telegram_post_id": int(row.telegram_post_id or 0),
                "forward_rate": round(rate, 4),
                "snippet": snippet,
                "published_at": row.published_at.isoformat() if row.published_at else "",
            }
        )
    return out


def _pick_bio_suggestion(*, momentum: float, posts_24h: float) -> str:
    templates = _bio_templates()
    if not templates:
        return "Макро и рынки — подпишитесь"
    if momentum < 0.35:
        return templates[0]
    if posts_24h >= 20:
        return templates[min(1, len(templates) - 1)]
    return templates[min(len(templates) - 1, 2)]


def decide_share_nudge_boost(*, momentum: float, silence_min: float | None) -> bool:
    """When acquisition is weak, boost forward nudge on wire posts."""
    if momentum >= 0.42:
        return False
    if silence_min is not None and float(silence_min) > 90:
        return True
    return momentum < 0.28


async def run_acquisition_loop(
    runtime_dir: str,
    *,
    channel_id: int | None,
    pulse: dict[str, Any],
) -> dict[str, Any]:
    """Weekly-ish acquisition recommendations + share-nudge auto-tuning."""
    result: dict[str, Any] = {"enabled": acquisition_loop_enabled()}
    if not acquisition_loop_enabled():
        result["reason"] = "disabled"
        return result

    momentum = float(pulse.get("engagement_momentum") or 0.0)
    pub_24h = float(pulse.get("published_24h") or 0)
    silence = pulse.get("silence_minutes")
    pin_candidates = await _top_forward_posts(channel_id=channel_id, limit=3)
    bio = _pick_bio_suggestion(momentum=momentum, posts_24h=pub_24h)
    boost_nudge = decide_share_nudge_boost(momentum=momentum, silence_min=silence)

    prev = _load_state(runtime_dir)
    pin_id = pin_candidates[0]["telegram_post_id"] if pin_candidates else 0
    pin_changed = pin_id and pin_id != int(prev.get("last_pin_candidate_id") or 0)

    state = {
        **prev,
        "pin_candidates": pin_candidates,
        "bio_suggestion": bio,
        "share_nudge_boost": boost_nudge,
        "last_pin_candidate_id": pin_id,
        "momentum": momentum,
    }
    _save_state(runtime_dir)

    if boost_nudge and os.getenv("CHANNEL_PRODUCT_SHARE_NUDGE", "true").strip().lower() not in {"0", "false", "no"}:
        os.environ["CHANNEL_PRODUCT_SHARE_NUDGE"] = "true"
        os.environ["ACQUISITION_SHARE_NUDGE_BOOST"] = "true"

    result.update(
        {
            "pin_candidates": pin_candidates,
            "bio_suggestion": bio,
            "share_nudge_boost": boost_nudge,
            "pin_changed": pin_changed,
        }
    )
    return result


def format_acquisition_operator_note(state: dict[str, Any]) -> str:
    lines = ["📌 Acquisition loop"]
    bio = str(state.get("bio_suggestion") or "").strip()
    if bio:
        lines.append(f"Bio: {bio}")
    pins = state.get("pin_candidates") or []
    if pins:
        top = pins[0]
        lines.append(f"Pin candidate: msg {top.get('telegram_post_id')} · fwd rate {top.get('forward_rate')}")
        snip = str(top.get("snippet") or "")[:80]
        if snip:
            lines.append(f"«{snip}…»")
    if state.get("share_nudge_boost"):
        lines.append("Share nudge: boosted (low momentum)")
    return "\n".join(lines)
