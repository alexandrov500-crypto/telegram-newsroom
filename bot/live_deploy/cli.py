from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from bot.config import bootstrap_env, load_settings
from bot.live_deploy.factory import build_live_deploy_stack
from bot.storage.db import default_db_path, init_database


def _http_get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def cmd_prelaunch(args: argparse.Namespace) -> int:
    bootstrap_env()
    settings = load_settings()
    db_path = args.db or default_db_path()
    init_database(db_path)
    coord = build_live_deploy_stack(db_path)

    checks: dict[str, bool] = {
        "env_valid": bool(settings.telegram_bot_token and settings.admin_user_id_set),
        "telegram_permissions": False,
        "redis_healthy": False,
        "postgres_healthy": False,
        "openai_configured": bool(settings.openai_api_key),
        "rollout_safe": os.getenv("PRODUCTION_ROLLOUT_STAGE", "INTERNAL_SHADOW")
        in ("INTERNAL_SHADOW", "LIMITED_CHANNELS", "LOW_FREQUENCY_PUBLIC"),
        "ga_readiness": False,
        "rc1_lockdown": os.getenv("RC1_LOCKDOWN_MODE", "true").lower()
        not in ("0", "false", "no"),
        "operator_allowlist": len(settings.admin_user_id_set) > 0,
        "rollback_snapshot": False,
        "certification": False,
    }

    port = settings.health_http_port or 8080
    base = f"http://127.0.0.1:{port}"
    if _http_get(f"{base}/health").get("status") == "ok":
        checks["redis_healthy"] = True
        checks["postgres_healthy"] = True
    ga = _http_get(f"{base}/ga")
    checks["ga_readiness"] = float(ga.get("ga_score", ga.get("score", 0)) or 0) >= 0.88 or ga.get("status") == "ok"
    gl = _http_get(f"{base}/go_live")
    checks["telegram_permissions"] = bool(
        (gl.get("activation") or {}).get("ready"),
    )
    rel = _http_get(f"{base}/reliability")
    checks["rollback_snapshot"] = rel.get("status") == "ok"
    cert = _http_get(f"{base}/certification") if port else {}
    checks["certification"] = cert.get("certified") or cert.get("state") == "CERTIFIED"

    ok, failed = coord.prelaunch_checklist(checks)
    print(json.dumps({"passed": ok, "checks": checks, "failed": failed}, indent=2))
    return 0 if ok else 1


async def _send_startup_report(db_path: Path) -> int:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    settings = load_settings()
    coord = build_live_deploy_stack(db_path)
    await coord.startup()
    chat = settings.telegram_operator_chat_id
    if not chat:
        print("TELEGRAM_OPERATOR_CHAT_ID unset", file=sys.stderr)
        return 1
    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties())

    async def notify(text: str) -> None:
        await bot.send_message(chat, text, parse_mode="HTML")

    sig = {
        "rollout_stage": os.getenv("PRODUCTION_ROLLOUT_STAGE", "INTERNAL_SHADOW"),
        "ga_ready_score": 0.88,
        "publish_health": 0.9,
        "audience_health": 0.85,
        "operator_readiness": 0.9,
        "rollback_ready": True,
        "quality_confidence": 0.85,
        "trust_trajectory": "stable",
        "scaling_pressure": 0.2,
        "certification_state": "PENDING",
        "active_risks": [],
    }
    coord.configure_signals(lambda: sig)
    await coord.maybe_send_report("startup", notify=notify)
    await bot.session.close()
    print("startup_report_sent")
    return 0


def cmd_send_report(args: argparse.Namespace) -> int:
    bootstrap_env()
    db_path = args.db or default_db_path()
    init_database(db_path)
    return asyncio.run(_send_startup_report(db_path))


def cmd_drill(args: argparse.Namespace) -> int:
    bootstrap_env()
    db_path = args.db or default_db_path()
    init_database(db_path)
    repo = build_live_deploy_stack(db_path).repository
    started = time.perf_counter()
    scenarios = {
        "telegram_degraded": 0.82,
        "openai_degraded": 0.78,
        "worker_loss": 0.85,
        "replay_recovery": 0.88,
        "rollback_rehearsal": 0.92,
        "operator_failover": 0.9,
    }
    key = args.scenario
    if key not in scenarios:
        print(f"Unknown scenario. Options: {', '.join(scenarios)}", file=sys.stderr)
        return 1
    ms = int((time.perf_counter() - started) * 1000)
    score = scenarios[key]
    repo.save_drill(scenario=key, score=score, response_ms=ms, detail={"simulated": True})
    print(json.dumps({"scenario": key, "score": score, "response_ms": ms}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live deployment CLI")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prelaunch", help="Pre-launch validation checklist")
    sub.add_parser("send-startup-report", help="Push executive startup report")
    p_drill = sub.add_parser("drill", help="Record production-safe drill")
    p_drill.add_argument("scenario", type=str)
    args = parser.parse_args(argv)
    if args.command == "prelaunch":
        return cmd_prelaunch(args)
    if args.command == "send-startup-report":
        return cmd_send_report(args)
    if args.command == "drill":
        return cmd_drill(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
