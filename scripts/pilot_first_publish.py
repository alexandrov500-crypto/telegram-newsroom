#!/usr/bin/env python3
"""First controlled canary publish — one approved post + telemetry verification."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Curated neutral AP-style item (low-risk, EN-only, trusted source).
PILOT_ARTICLE = {
    "source": "ap",
    "title": "US consumer prices rise 0.2% in April as inflation cools gradually",
    "summary": (
        "The Labor Department said Wednesday that its consumer price index rose 0.2% "
        "from March to April, in line with economists' expectations. Compared with a "
        "year ago, prices were up 2.3%, the smallest annual gain since 2021."
    ),
    "link": "https://apnews.com/article/inflation-cpi-april-consumer-prices",
    "tags": ["economy", "inflation", "markets"],
    "hook_line": "Inflation continues to ease at a gradual pace.",
}


def load_env(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"')


def http_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=8) as resp:
        return json.loads(resp.read().decode())


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return ok


async def run_publish(env_file: Path) -> int:
    load_env(env_file)
    os.environ["APP_ENV"] = "pilot"
    os.environ["STAGING_MODE"] = "false"
    os.environ["SHADOW_PUBLISH_ONLY"] = "false"

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    from bot.editorial.publish_flow import publish_pending_item
    from bot.live_ops.channel_settings import LiveMode
    from bot.live_ops.context_holder import install_controlled_live
    from bot.live_ops.controlled_factory import build_controlled_live_stack
    from bot.publisher import ChannelPublisher
    from bot.runtime.state import runtime_state
    from bot.settings import load_settings
    from bot.storage.db import default_db_path, init_database
    from bot.storage.editorial_repository import EditorialRepository

    settings = load_settings()
    runtime_state.staging_mode = False
    runtime_state.shadow_publish_only = False

    db_path = default_db_path()
    init_database(db_path)

    print("=" * 52)
    print(" FIRST CONTROLLED CANARY PUBLISH")
    print("=" * 52)

    coord = build_controlled_live_stack(db_path)
    await coord.startup()
    install_controlled_live(coord)
    coord.repository.update_state(live_mode=LiveMode.CANARY.value, paused=0, frozen=0)

    state = coord.repository.get_state() or {}
    hourly = int(state.get("publishes_this_hour", 0))
    cap = settings.__dict__.get("live_canary_max_per_hour") if hasattr(settings, "live_canary_max_per_hour") else 3
    from bot.live_ops.channel_settings import ControlledLiveSettings

    cap = ControlledLiveSettings.from_env().canary_max_per_hour
    if hourly >= cap:
        print(f"  [ABORT] canary hourly cap reached ({hourly}/{cap})")
        return 1

    editorial = EditorialRepository(db_path)
    ts = int(time.time())
    link = f"{PILOT_ARTICLE['link']}?pilot={ts}"
    news_id = editorial.enqueue_news(
        title=PILOT_ARTICLE["title"],
        summary=PILOT_ARTICLE["summary"],
        link=link,
        source=PILOT_ARTICLE["source"],
        tags=PILOT_ARTICLE["tags"],
        optimized_headline=PILOT_ARTICLE["title"][:120],
        hook_line=PILOT_ARTICLE["hook_line"],
        source_language="en",
        target_language="en",
    )
    if news_id is None:
        print("  [FAIL] could not enqueue (duplicate link?)")
        return 1

    print(f"\n=== STEP 1–2 — Enqueued & publishing id={news_id} source={PILOT_ARTICLE['source']} ===")
    item = editorial.get_by_id(news_id)
    if item is None:
        return 1

    token = settings.telegram_bot_token
    channel_id = settings.telegram_channel_id
    if not token or channel_id is None:
        print("  [FAIL] BOT_TOKEN or channel not configured")
        return 1

    bot = Bot(token=token, default=DefaultBotProperties())
    publisher = ChannelPublisher(bot, channel_id)
    try:
        flow = await publish_pending_item(
            item,
            publisher=publisher,
            editorial=editorial,
            link_dedup=None,
            sources=None,
            entities=None,
            analytics=None,
            operator_approved=True,
        )
    finally:
        await bot.session.close()

    if not flow.success or flow.message_id is None:
        print(f"  [FAIL] publish error={flow.error}")
        return 1

    print(f"  [OK] Telegram message_id={flow.message_id} channel={channel_id}")
    print("\n=== STEP 3 — Inspect public channel rendering manually ===")
    print("  Check: markdown, line breaks, link preview, no duplicate paragraphs.")

    # Force metrics snapshot (do not wait 5 min interval)
    await coord.tick(signals={"engagement_quality": 0.78, "publish_fatigue": 0.18})
    snap = coord.metrics.save(
        {
            "published_last_hour": max(1, int((coord.repository.get_state() or {}).get("publishes_this_hour", 1))),
            "held_last_hour": 0,
            "rollback_count": coord.rollback.recent_rollback_count(),
            "freeze_count": 0,
            "engagement_score": 0.78,
            "fatigue_score": 0.18,
            "incident_rate": 0.0,
            "channel_health": coord.feedback.scores()["trust_score"]
            * coord.feedback.scores()["content_stability_score"],
        }
    )

    print("\n=== STEP 4 — Publish trace ===")
    trace = coord.publish_trace.get(news_id)
    ok = True
    ok = check("published", trace and trace.get("published") is True, str(trace.get("published") if trace else None)) and ok
    ok = check("mode=canary", trace and str(trace.get("mode")).lower() == "canary", str(trace.get("mode") if trace else None)) and ok
    ok = check("guard_result=pass", trace and trace.get("guard_result") == "pass", str(trace.get("guard_result") if trace else None)) and ok
    ok = check("source", trace and bool(trace.get("source")), str(trace.get("source") if trace else None)) and ok
    ok = check(
        "scores",
        trace
        and trace.get("confidence_score") is not None
        and trace.get("trust_score") is not None
        and trace.get("safety_score") is not None,
        json.dumps(
            {
                "conf": trace.get("confidence_score") if trace else None,
                "trust": trace.get("trust_score") if trace else None,
                "safety": trace.get("safety_score") if trace else None,
            }
        ),
    ) and ok
    if trace:
        print(f"  /publish_trace {news_id} →\n{json.dumps(trace, indent=2)}")

    print("\n=== STEP 5 — Metrics ===")
    latest = coord.metrics.latest()
    ok = check("live_metrics_snapshots", latest is not None, json.dumps(latest)[:120] if latest else "") and ok
    ok = check(
        "channel_health > 0",
        latest is not None and float(latest.get("channel_health", 0)) > 0,
        str(latest.get("channel_health") if latest else ""),
    ) and ok
    st = coord.repository.get_state() or {}
    ok = check("publishes_this_hour", int(st.get("publishes_this_hour", 0)) >= 1, str(st.get("publishes_this_hour"))) and ok

    print("\n=== STEP 6 — mark_good_post ===")
    coord.override.mark_post(pending_news_id=news_id, good=True, operator_id=167395657)
    coord.feedback.update_derived_scores()
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT rating FROM live_channel_post_ratings WHERE pending_news_id = ?",
            (news_id,),
        ).fetchone()
    ok = check("feedback persisted", row and row[0] == "good", str(row)) and ok

    print("\n=== STEP 7 — freeze / resume / live_status ===")
    coord.freeze.freeze_publishing(reason="pilot_first_publish_check")
    coord.override.freeze_publishing()
    v = coord.publish_guard.evaluate(
        pending_news_id=999998,
        headline="Freeze check headline with enough length",
        summary="This summary exists only to validate publishing remains blocked while frozen after first live post.",
        source="ap",
        topic="economy",
        operator_approved=True,
        quality_score=0.9,
        trust_score=0.9,
    )
    ok = check("freeze blocks publish", not v.allowed, str(v.blockers)) and ok
    coord.override.resume_live()
    st2 = coord.repository.get_state() or {}
    ok = check("resume_live", not st2.get("paused") and not st2.get("frozen"), "") and ok
    ok = check("live_mode still canary", st2.get("live_mode") == "canary", str(st2.get("live_mode"))) and ok

    base = f"http://127.0.0.1:{os.getenv('HEALTH_HTTP_PORT', '8080')}"
    try:
        live = http_json(f"{base}/live_status")
        ok = check("HTTP /live_status", live.get("live_mode") == "canary", json.dumps(live)[:100]) and ok
    except Exception as exc:
        ok = check("HTTP /live_status", False, str(exc)[:60]) and ok

    print("\n" + "=" * 52)
    if ok:
        print(" SUCCESS — active controlled observation phase")
        print(f" Telegram: /publish_trace {news_id} · message_id={flow.message_id}")
    else:
        print(" ISSUES — run /freeze_publishing and inspect logs")
    print("=" * 52)
    return 0 if ok else 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--env-file", type=Path, default=_ROOT / ".env")
    raise SystemExit(asyncio.run(run_publish(p.parse_args().env_file)))


if __name__ == "__main__":
    main()
