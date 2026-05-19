#!/usr/bin/env python3
"""End-to-end controlled canary publish validation with runtime observation."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# STEP 1 — curated AP neutral economics item (trusted, low-risk, EN-only).
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
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"')


def http_json(url: str, timeout: float = 6.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def observe_runtime(base: str, label: str) -> dict[str, Any]:
    snap: dict[str, Any] = {"label": label, "ts": time.time()}
    for path in (
        "/runtime_identity",
        "/runtime_performance",
        "/runtime_loops",
        "/live_status",
        "/channel_health",
    ):
        try:
            snap[path] = http_json(f"{base.rstrip('/')}{path}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            snap[path] = {"error": str(exc)[:120]}
    return snap


def print_runtime_observation(snap: dict[str, Any]) -> None:
    print(f"\n--- Runtime observation: {snap.get('label')} ---")
    ident = snap.get("/runtime_identity", {})
    loops = snap.get("/runtime_loops", {})
    perf = snap.get("/runtime_performance", {})
    live = snap.get("/live_status", {})
    print(
        f"  instance={ident.get('runtime_instance_id')} "
        f"profile={ident.get('runtime_profile')} "
        f"watchdog={ident.get('watchdog_active')}",
    )
    stalled = loops.get("stalled") or []
    print(f"  stalled_loops={stalled or 'none'}")
    lag = perf.get("event_loop_lag_max") or perf.get("last_lag_sec")
    if lag is not None:
        print(f"  event_loop_lag={lag}")
    mode = live.get("live_mode") or (live.get("state") or {}).get("live_mode")
    frozen = live.get("frozen") or (live.get("state") or {}).get("frozen")
    pub_h = (live.get("state") or {}).get("publishes_this_hour") or live.get("publishes_this_hour")
    print(f"  live_mode={mode} frozen={frozen} publishes_this_hour={pub_h}")


async def run_validation(env_file: Path, *, skip_publish: bool) -> int:
    load_env(env_file)
    os.environ.setdefault("APP_ENV", "pilot")
    os.environ.setdefault("RUNTIME_PROFILE", "minimal_pilot")
    os.environ.setdefault("LIVE_MODE", "canary")

    base = f"http://127.0.0.1:{os.getenv('HEALTH_HTTP_PORT', '8080')}"
    print("=" * 58)
    print(" CANARY E2E PUBLISH VALIDATION")
    print("=" * 58)

    ok = True
    baseline = observe_runtime(base, "baseline")
    print_runtime_observation(baseline)
    ok = check(
        "runtime_identity minimal_pilot",
        (baseline.get("/runtime_identity") or {}).get("runtime_profile") == "minimal_pilot",
        str((baseline.get("/runtime_identity") or {}).get("runtime_profile")),
    ) and ok
    ok = check(
        "no stalled loops (baseline)",
        not (baseline.get("/runtime_loops") or {}).get("stalled"),
        str((baseline.get("/runtime_loops") or {}).get("stalled")),
    ) and ok

    if skip_publish:
        print("\n[SKIP] --no-publish")
        return 0 if ok else 1

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    from bot.editorial.publish_flow import publish_pending_item
    from bot.live_ops.channel_settings import ControlledLiveSettings, LiveMode
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

    coord = build_controlled_live_stack(db_path)
    await coord.startup()
    install_controlled_live(coord)
    coord.repository.update_state(live_mode=LiveMode.CANARY.value, paused=0, frozen=0)

    cap = ControlledLiveSettings.from_env().canary_max_per_hour
    hourly = int((coord.repository.get_state() or {}).get("publishes_this_hour", 0))
    if hourly >= cap:
        print(f"\n[ABORT] canary hourly cap reached ({hourly}/{cap})")
        return 1

    print("\n=== STEP 1–2 — Safe AP content + operator-approved publish ===")
    editorial = EditorialRepository(db_path)
    ts = int(time.time())
    link = f"{PILOT_ARTICLE['link']}?canary_e2e={ts}"
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
        print("  [FAIL] enqueue failed (duplicate link?)")
        return 1
    print(f"  pending_news_id={news_id} source={PILOT_ARTICLE['source']}")

    item = editorial.get_by_id(news_id)
    if item is None:
        return 1

    token = settings.telegram_bot_token
    channel_id = settings.telegram_channel_id
    if not token or channel_id is None:
        print("  [FAIL] BOT_TOKEN or TELEGRAM_CHANNEL_ID missing")
        return 1

    during_before = observe_runtime(base, "pre-publish")
    print_runtime_observation(during_before)

    bot = Bot(token=token, default=DefaultBotProperties())
    publisher = ChannelPublisher(bot, channel_id)
    t0 = time.perf_counter()
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
    publish_sec = time.perf_counter() - t0

    during_after = observe_runtime(base, "post-publish")
    print_runtime_observation(during_after)

    ok = check("publish latency < 30s", publish_sec < 30.0, f"{publish_sec:.2f}s") and ok
    ok = check(
        "no stalled loops (post-publish)",
        not (during_after.get("/runtime_loops") or {}).get("stalled"),
        str((during_after.get("/runtime_loops") or {}).get("stalled")),
    ) and ok
    ok = check(
        "runtime still minimal_pilot",
        (during_after.get("/runtime_identity") or {}).get("runtime_profile") == "minimal_pilot",
        str((during_after.get("/runtime_identity") or {}).get("runtime_instance_id")),
    ) and ok

    if not flow.success or flow.message_id is None:
        print(f"  [FAIL] publish error={flow.error}")
        return 1

    ok = check("Telegram publish", True, f"message_id={flow.message_id} channel={channel_id}") and ok
    print("\n=== STEP 4 — Manual Telegram rendering check ===")
    print(f"  Open channel {channel_id} — verify markdown, links, no dup paragraphs.")
    print(f"  https://t.me/c/{str(channel_id).replace('-100', '')}/{flow.message_id}")

    await coord.tick(signals={"engagement_quality": 0.78, "publish_fatigue": 0.18})

    print("\n=== STEP 5 — Publish trace ===")
    trace = coord.publish_trace.get(news_id)
    ok = check("trace exists", trace is not None) and ok
    if trace:
        ok = check("published=true", trace.get("published") is True) and ok
        ok = check("mode=canary", str(trace.get("mode", "")).lower() == "canary", str(trace.get("mode"))) and ok
        ok = check("guard_result=pass", trace.get("guard_result") == "pass", str(trace.get("guard_result"))) and ok
        ok = check("source populated", bool(trace.get("source")), str(trace.get("source"))) and ok
        if trace.get("cluster_id") is not None or item.cluster_id is not None:
            ok = check("cluster_id", True, str(trace.get("cluster_id") or item.cluster_id)) and ok
        else:
            print(
                "  [NOTE] cluster_id empty — direct enqueue path; "
                "full RSS→cluster pipeline assigns cluster on ingest",
            )
        ok = check(
            "scores present",
            trace.get("confidence_score") is not None
            and trace.get("trust_score") is not None
            and trace.get("safety_score") is not None,
            json.dumps(
                {
                    "conf": trace.get("confidence_score"),
                    "trust": trace.get("trust_score"),
                    "safety": trace.get("safety_score"),
                },
            ),
        ) and ok
        hold = trace.get("hold_reason")
        ok = check("hold_reason empty", not hold, str(hold)) and ok
        ok = check("timestamp", bool(trace.get("timestamp") or trace.get("created_at"))) and ok
        print(f"  /publish_trace {news_id}:\n{json.dumps(trace, indent=2)}")
        print(f"\n  Operator command: /publish_trace {news_id}")

    print("\n=== STEP 6 — Metrics ===")
    latest = coord.metrics.latest()
    ok = check("live_metrics_snapshots", latest is not None, json.dumps(latest)[:140] if latest else "") and ok
    st = coord.repository.get_state() or {}
    ok = check("publishes_this_hour >= 1", int(st.get("publishes_this_hour", 0)) >= 1, str(st.get("publishes_this_hour"))) and ok

    print("\n=== STEP 7 — mark_good_post ===")
    coord.override.mark_post(pending_news_id=news_id, good=True, operator_id=167395657)
    coord.feedback.update_derived_scores()
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT rating FROM live_channel_post_ratings WHERE pending_news_id = ?",
            (news_id,),
        ).fetchone()
    ok = check("feedback persisted (good)", row and row[0] == "good", str(row)) and ok

    print("\n=== STEP 8 — freeze / resume / live_status ===")
    coord.freeze.freeze_publishing(reason="canary_e2e_validation")
    coord.override.freeze_publishing()
    verdict = coord.publish_guard.evaluate(
        pending_news_id=999997,
        headline="Freeze validation headline with sufficient length",
        summary="Summary used only to confirm publish guard blocks while channel is frozen after canary validation.",
        source="ap",
        topic="economy",
        operator_approved=True,
        quality_score=0.9,
        trust_score=0.9,
    )
    ok = check("freeze blocks publish", not verdict.allowed, str(verdict.blockers)[:80]) and ok
    coord.override.resume_live()
    st2 = coord.repository.get_state() or {}
    ok = check("resume_live", not st2.get("paused") and not st2.get("frozen")) and ok
    ok = check("live_mode=canary", st2.get("live_mode") == "canary", str(st2.get("live_mode"))) and ok

    final = observe_runtime(base, "final")
    print_runtime_observation(final)

    print("\n" + "=" * 58)
    if ok:
        print(" SUCCESS — pilot enters active operational observation phase")
        print(f"  pending_news_id={news_id}  telegram_message_id={flow.message_id}")
        print(f"  /publish_trace {news_id}  /mark_good_post {news_id}")
    else:
        print(" FAILURE — run /freeze_publishing and inspect logs")
        print("  python3 scripts/runtime_process_check.py")
    print("=" * 58)
    return 0 if ok else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Canary E2E publish validation")
    p.add_argument("--env-file", type=Path, default=_ROOT / ".env")
    p.add_argument("--no-publish", action="store_true", help="Runtime checks only")
    raise SystemExit(asyncio.run(run_validation(p.parse_args().env_file, skip_publish=p.parse_args().no_publish)))


if __name__ == "__main__":
    main()
