#!/usr/bin/env python3
"""Controlled public pilot — operational verification (not a load test)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"')


def http_json(url: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


async def verify_runtime_http(base: str) -> bool:
    print("\n=== STEP 2 — Runtime health (HTTP) ===")
    ok = True
    for path, keys in (
        ("/health", ("status",)),
        ("/live_status", ("status",)),
        ("/pilot_readiness", ("ready",)),
        ("/channel_health", ("status",)),
    ):
        try:
            body = http_json(f"{base.rstrip('/')}{path}")
            passed = body.get("status") == "ok" or body.get("ready") is True
            if path == "/live_status":
                mode = body.get("live_mode") or (body.get("state") or {}).get("live_mode")
                frozen = body.get("frozen") or (body.get("state") or {}).get("frozen")
                detail = f"mode={mode} frozen={frozen}"
                passed = passed and str(mode).lower() == "canary"
            elif path == "/pilot_readiness":
                detail = f"ready={body.get('ready')}"
            else:
                detail = str(body.get("status", body.get("ready", "")))[:60]
            ok = check(path, passed, detail) and ok
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            ok = check(path, False, str(exc)[:80]) and ok
    return ok


def verify_persistence(db_path: Path) -> bool:
    print("\n=== STEP 3 — Persistence ===")
    import sqlite3

    from bot.live_ops.pilot_readiness import persistence_snapshot
    from bot.storage.db import init_database

    init_database(db_path)
    snap = persistence_snapshot(db_path)
    ok = True
    for key in ("trace_count", "metrics_count", "incidents_count"):
        ok = check(f"snapshot.{key}", snap.get(key, -1) >= 0, str(snap.get(key))) and ok

    with sqlite3.connect(db_path) as conn:
        for table in (
            "live_publish_trace",
            "live_metrics_snapshots",
            "live_channel_incidents",
            "live_channel_state",
        ):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                ok = check(f"table {table}", True, f"rows={n}") and ok
            except sqlite3.OperationalError as exc:
                ok = check(f"table {table}", False, str(exc)[:60]) and ok
    return ok


async def simulate_dashboard(coord) -> bool:
    print("\n=== STEP 2b — /live_dashboard (coordinator) ===")
    try:
        html = coord.dashboard_html(coord._signals_fn() if coord._signals_fn else {})
        ok = bool(html) and "degraded" not in html.lower()[:80]
        return check("/live_dashboard", ok, f"{len(html)} chars")
    except Exception as exc:
        return check("/live_dashboard", False, str(exc)[:80])


async def first_controlled_publish(db_path: Path, *, dry_run: bool) -> tuple[bool, int | None]:
    print("\n=== STEP 4 — First controlled publish ===")
    if dry_run:
        print("  [SKIP] --no-publish")
        return True, None

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    from bot.editorial.publish_flow import publish_pending_item
    from bot.live_ops.context_holder import install_controlled_live
    from bot.live_ops.controlled_factory import build_controlled_live_stack
    from bot.publisher import ChannelPublisher
    from bot.runtime.state import runtime_state
    from bot.settings import load_settings
    from bot.storage.db import init_database
    from bot.storage.editorial_repository import EditorialRepository

    settings = load_settings()
    runtime_state.staging_mode = False
    runtime_state.shadow_publish_only = False

    token = settings.telegram_bot_token
    channel_id = settings.telegram_channel_id
    if not token or channel_id is None:
        check("publish prerequisites", False, "BOT_TOKEN or channel missing")
        return False, None

    init_database(db_path)
    coord = build_controlled_live_stack(db_path)
    await coord.startup()
    install_controlled_live(coord)

    editorial = EditorialRepository(db_path)
    ts = int(time.time())
    link = f"https://www.reuters.com/pilot-verify-{ts}"
    news_id = editorial.enqueue_news(
        title="Pilot verification — controlled canary post",
        summary=(
            "Controlled public pilot: single approved canary publish for operational "
            "verification. Safe to delete after review."
        ),
        link=link,
        source="reuters",
        tags=["pilot", "verification"],
        optimized_headline="Pilot verification — controlled canary",
        hook_line="Operational canary check",
    )
    if news_id is None:
        check("enqueue pending item", False, "duplicate link?")
        return False, None
    check("enqueue pending item", True, f"id={news_id}")

    item = editorial.get_by_id(news_id)
    if item is None:
        check("load pending item", False, "")
        return False, None

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

    ok = flow.success and flow.message_id is not None
    check(
        "publish to public channel",
        ok,
        f"message_id={flow.message_id} error={flow.error or 'none'}",
    )
    return ok, news_id if ok else None


def verify_publish_trace(db_path: Path, news_id: int) -> bool:
    print("\n=== STEP 5 — Publish trace ===")
    from bot.live_ops.publish_trace import PublishTraceStore

    trace = PublishTraceStore(db_path).get(news_id)
    if not trace:
        return check("publish_trace row", False, "missing")
    ok = True
    ok = check("published", trace.get("published") is True, str(trace.get("published"))) and ok
    ok = check("mode=canary", str(trace.get("mode", "")).lower() == "canary", str(trace.get("mode"))) and ok
    ok = check(
        "scores populated",
        trace.get("confidence_score") is not None and trace.get("trust_score") is not None,
        f"conf={trace.get('confidence_score')} trust={trace.get('trust_score')}",
    ) and ok
    ok = check(
        "guard_result",
        str(trace.get("guard_result", "")).lower() in ("pass", "ok", "published"),
        str(trace.get("guard_result")),
    ) and ok
    ok = check("source", bool(trace.get("source")), str(trace.get("source"))) and ok
    ok = check("timestamp", bool(trace.get("timestamp")), str(trace.get("timestamp", ""))[:24]) and ok
    print(f"  trace: {json.dumps(trace, indent=2)[:500]}")
    return ok


def verify_feedback(db_path: Path, news_id: int) -> bool:
    print("\n=== STEP 6 — Feedback calibration ===")
    from bot.live_ops.controlled_factory import build_controlled_live_stack

    coord = build_controlled_live_stack(db_path)
    coord.override.mark_post(pending_news_id=news_id, good=True, operator_id=167395657)
    coord.feedback.update_derived_scores()
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT rating FROM live_channel_post_ratings WHERE pending_news_id = ?",
            (news_id,),
        ).fetchone()
    ok = check("mark_good_post persistence", row and row[0] == "good", str(row))
    scores = coord.feedback.scores()
    check("feedback scores", True, json.dumps(scores)[:80])
    return ok


async def verify_safety(db_path: Path) -> bool:
    print("\n=== STEP 7 — Safety (freeze / resume) ===")
    from bot.live_ops.channel_settings import LiveMode
    from bot.live_ops.controlled_factory import build_controlled_live_stack
    from bot.runtime.state import runtime_state

    coord = build_controlled_live_stack(db_path)
    runtime_state.shadow_publish_only = False
    coord.repository.update_state(live_mode=LiveMode.CANARY.value, paused=0, frozen=0)
    coord.freeze.freeze_publishing(reason="pilot_e2e_verify")
    coord.override.freeze_publishing()
    frozen = coord.repository.get_state() or {}
    ok = check("freeze_publishing", bool(frozen.get("frozen")) and bool(frozen.get("paused")), "")
    verdict = coord.publish_guard.evaluate(
        pending_news_id=999999,
        headline="Test headline for freeze check only",
        summary="This summary is long enough to pass content checks during freeze verification.",
        source="reuters",
        topic="pilot",
        operator_approved=True,
        quality_score=0.9,
        trust_score=0.9,
    )
    ok = check(
        "publish blocked while frozen",
        not verdict.allowed and "freeze" in verdict.reason.lower()
        or "frozen" in str(verdict.blockers),
        f"{verdict.reason} blockers={verdict.blockers}",
    ) and ok
    coord.override.resume_live()
    resumed = coord.repository.get_state() or {}
    ok = check(
        "resume_live",
        not bool(resumed.get("paused")) and not bool(resumed.get("frozen")),
        f"paused={resumed.get('paused')} frozen={resumed.get('frozen')}",
    ) and ok
    return ok


async def main_async(args: argparse.Namespace) -> int:
    env_file = args.env_file
    load_env_file(env_file)
    os.environ.setdefault("APP_ENV", "pilot")
    os.environ["STAGING_MODE"] = "false"
    os.environ["STAGING_STRICT_STARTUP"] = "false"

    from bot.storage.db import default_db_path, init_database

    db_path = default_db_path()
    init_database(db_path)
    base = f"http://127.0.0.1:{os.getenv('HEALTH_HTTP_PORT', '8080')}"

    print("=" * 52)
    print(" CONTROLLED PUBLIC PILOT — E2E VERIFICATION")
    print("=" * 52)
    print(f"  time: {datetime.now(timezone.utc).isoformat()}")
    print(f"  db:   {db_path}")

    all_ok = True

    if args.activate:
        print("\n=== STEP 1 — Activate (preflight) ===")
        import subprocess

        r = subprocess.run(
            ["bash", "scripts/pilot_activate.sh"],
            cwd=_ROOT,
            env={**os.environ, "ENV_FILE": str(env_file.name)},
        )
        all_ok = check("pilot_activate.sh", r.returncode == 0) and all_ok
        time.sleep(3)
    else:
        print("\n=== STEP 1 — Operator runtime ===")
        try:
            http_json(f"{base}/health")
            all_ok = check("operator /health", True) and all_ok
        except Exception as exc:
            all_ok = check("operator /health", False, str(exc)[:80]) and all_ok

    all_ok = (await verify_runtime_http(base)) and all_ok

    from bot.live_ops.controlled_factory import build_controlled_live_stack

    coord = build_controlled_live_stack(db_path)
    all_ok = (await simulate_dashboard(coord)) and all_ok

    all_ok = verify_persistence(db_path) and all_ok

    pub_ok, news_id = await first_controlled_publish(db_path, dry_run=args.no_publish)
    all_ok = pub_ok and all_ok

    if news_id is not None:
        all_ok = verify_publish_trace(db_path, news_id) and all_ok
        all_ok = verify_feedback(db_path, news_id) and all_ok

    all_ok = (await verify_safety(db_path)) and all_ok

    print("\n" + "=" * 52)
    if all_ok:
        print(" PILOT E2E: SUCCESS — controlled public observation mode")
    else:
        print(" PILOT E2E: ISSUES — freeze first, inspect logs/traces, resume later")
    print("=" * 52)
    return 0 if all_ok else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Controlled pilot E2E verification")
    p.add_argument("--env-file", type=Path, default=_ROOT / ".env")
    p.add_argument("--activate", action="store_true", help="Run pilot_activate.sh first")
    p.add_argument("--no-publish", action="store_true", help="Skip real channel publish")
    raise SystemExit(asyncio.run(main_async(p.parse_args())))


if __name__ == "__main__":
    main()
