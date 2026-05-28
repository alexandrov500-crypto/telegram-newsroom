#!/usr/bin/env python3
"""
Final staging GO/NO-GO validator (PUBLIC LAUNCH READY checklist).

Usage:
  python3 tools/final_staging_validator.py
  python3 tools/final_staging_validator.py --health-url http://127.0.0.1:8080/health
  python3 tools/final_staging_validator.py --strict
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pgrep_app_main() -> list[str]:
    try:
        out = subprocess.run(
            ["pgrep", "-fl", "app.main"],
            capture_output=True,
            text=True,
            check=False,
        )
        return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    except OSError:
        return []


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return (out.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _fetch_health(url: str, timeout: float = 5.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_runtime_markers(runtime_dir: Path, issues: list[str], warnings: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    active_path = runtime_dir / "active_runtime.json"
    lock_path = runtime_dir / "newsroom.lock"
    out["active_runtime_exists"] = active_path.is_file()
    out["lock_exists"] = lock_path.is_file()

    if active_path.is_file():
        try:
            data = json.loads(active_path.read_text(encoding="utf-8"))
            out["active_runtime"] = data
            apid = int(data.get("pid") or 0)
            alive = _pid_alive(apid)
            out["active_runtime_pid_alive"] = alive
            if not alive:
                issues.append(f"stale active_runtime.json pid={apid} (process dead)")
            elif len(_pgrep_app_main()) == 0:
                warnings.append(f"active_runtime pid={apid} alive but no app.main in pgrep")
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"active_runtime.json unreadable: {exc}")

    procs = _pgrep_app_main()
    out["app_main_processes"] = procs
    if len(procs) > 1:
        issues.append(f"multiple app.main processes: {len(procs)}")
    elif len(procs) == 0:
        warnings.append("no app.main process (validator may run before start)")

    return out


def _check_staging_health(staging: dict[str, Any], issues: list[str], warnings: list[str]) -> None:
    if not staging:
        issues.append("/health missing staging block")
        return

    if staging.get("transport_layer_ok") is not True:
        pub = staging.get("publishing") or {}
        if int(pub.get("published_1h") or 0) > 0:
            warnings.append("transport_layer_ok false but published_1h>0 — retry remaining failed drafts")
        else:
            issues.append("staging.transport_layer_ok is not true")

    if staging.get("launch_ready") is not True:
        for alert in staging.get("alerts") or []:
            if alert.get("severity") == "critical":
                issues.append(f"critical alert: {alert.get('code')}")

    pub = staging.get("publishing") or {}
    if int(pub.get("drafts_failed") or 0) > 0:
        warnings.append(f"drafts_failed={pub.get('drafts_failed')}")
    err = pub.get("last_publish_error") or {}
    err_txt = str(err.get("error") or "")
    if "disable_web_page_preview" in err_txt:
        issues.append("last_publish_error contains legacy disable_web_page_preview")

    bot = staging.get("bot") or {}
    if bot.get("polling_active") is False:
        warnings.append("bot polling_active=false")
    if int(bot.get("handler_errors_total") or 0) > 50:
        warnings.append(f"elevated handler_errors_total={bot.get('handler_errors_total')}")

    pipeline = staging.get("pipeline") or {}
    stuck = pipeline.get("stuck_jobs") or []
    if stuck:
        ages = [float(s.get("age_sec") or 0) for s in stuck if isinstance(s, dict)]
        if ages and max(ages) >= float(os.getenv("PIPELINE_STUCK_TICK_SEC", "900")):
            issues.append(f"stuck pipeline ticks: {len(stuck)}")

    runtime = staging.get("runtime") or {}
    if runtime.get("singleton_lock_status") not in ("owner", True) and runtime.get("singleton_lock_owner") is not True:
        warnings.append(f"singleton not owner: {runtime.get('singleton_lock_status')}")


def _check_soft_launch(issues: list[str], warnings: list[str]) -> dict[str, Any]:
    from app.editorial.soft_launch import is_soft_launch_mode, soft_launch_thresholds

    enabled = is_soft_launch_mode()
    th = soft_launch_thresholds().to_dict()
    if not enabled:
        warnings.append("SOFT_LAUNCH_MODE is not enabled (recommended for 7-day burn-in)")
    return {"enabled": enabled, "thresholds": th}


def _check_public_output_lock(issues: list[str]) -> dict[str, Any]:
    from app.editorial.public_output_lock import enforce_public_output_lock
    from publisher.public_renderer import render_public_post_html

    sample_debug = "Quality: 0.9\nDuplicates: 2\n\nApple удалила приложения."
    html = render_public_post_html(sample_debug, "[]")
    lock = enforce_public_output_lock(html)
    if lock.blocked:
        issues.append(f"public renderer still leaks: {lock.violations}")
    clean = render_public_post_html("Apple удалила приложения из App Store.", "[]")
    lock2 = enforce_public_output_lock(clean)
    return {"debug_sample_violations": list(lock.violations), "clean_ok": lock2.ok}


def _check_editorial_safety(issues: list[str]) -> dict[str, Any]:
    from app.editorial.final_publish_gate import evaluate_final_publish_gate
    from app.editorial.scoring_engine import score_story

    tabloid = "Шокирующая правда: эскорт-экономика и проституция как бизнес"
    escore = score_story(text=tabloid, sources=["@random"])
    gate = evaluate_final_publish_gate(content=tabloid, sources="[]", operator_approved=False)
    if gate.allowed:
        issues.append("final gate allowed tabloid/adult sample")
    return {"tabloid_blocked": not gate.allowed, "reason": gate.reason}


def _check_forensic_module(issues: list[str]) -> dict[str, Any]:
    try:
        import publisher.telegram_forensic as tf
        import publisher.telegram_transport as tt
        from publisher.telegram_forensic import forensic_media_enabled

        return {
            "transport_file": tt.__file__,
            "forensic_file": tf.__file__,
            "forensic_enabled": forensic_media_enabled(),
        }
    except Exception as exc:
        issues.append(f"transport/forensic import failed: {exc}")
        return {}


def _check_recent_ticks(runtime_dir: Path, issues: list[str], warnings: list[str]) -> dict[str, Any]:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path or not Path(path).is_file():
        warnings.append("no sqlite DB for tick validation")
        return {}
    import sqlite3

    conn = sqlite3.connect(str(path), timeout=2.0)
    try:
        rows = conn.execute(
            """
            SELECT status, posts_collected, drafts_created, finished_at, detail_json
            FROM pipeline_ticks ORDER BY id DESC LIMIT 7
            """
        ).fetchall()
        failed = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE status='failed'"
        ).fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE status IN ('pending','publishing')"
        ).fetchone()
    finally:
        conn.close()
    ticks = []
    for r in rows:
        detail = {}
        try:
            detail = json.loads(r[4] or "{}")
        except Exception:
            pass
        ticks.append(
            {
                "status": r[0],
                "posts_collected": r[1],
                "drafts_created": r[2],
                "finished_at": r[3],
                "publish_outcome": detail.get("publish_outcome"),
            }
        )
    ok_ticks = [t for t in ticks if t.get("status") == "ok"]
    if len(ok_ticks) < 3:
        warnings.append(f"fewer than 3 recent ok pipeline ticks ({len(ok_ticks)})")
    stuck_drafts = int(pending[0] if pending else 0)
    if stuck_drafts > 12:
        warnings.append(f"many pending/publishing drafts: {stuck_drafts}")
    return {
        "recent_ticks": ticks,
        "ok_tick_count": len(ok_ticks),
        "drafts_failed": int(failed[0] if failed else 0),
        "drafts_pending_or_publishing": stuck_drafts,
    }


def _check_trust_layer() -> dict[str, Any]:
    from app.editorial.trust_system import evaluate_editorial_trust
    from app.editorial.scoring_engine import score_story

    text = "Росстат: инфляция замедлилась по официальным данным."
    escore = score_story(text=text, sources=["@cb_economics", "@vedofon"])
    trust = evaluate_editorial_trust(text, escore, sources=["@cb_economics", "@vedofon"])
    return trust.to_dict()


def run_validator(*, health_url: str, strict: bool) -> int:
    issues: list[str] = []
    warnings: list[str] = []
    report: dict[str, Any] = {
        "git_head": _git_head(),
        "health_url": health_url,
        "phase": "final_staging",
    }

    runtime_dir = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    report["runtime"] = _check_runtime_markers(runtime_dir, issues, warnings)
    report["forensic"] = _check_forensic_module(issues)
    report["ticks"] = _check_recent_ticks(runtime_dir, issues, warnings)
    report["soft_launch"] = _check_soft_launch(issues, warnings)
    report["public_output_lock"] = _check_public_output_lock(issues)
    report["editorial_safety"] = _check_editorial_safety(issues)
    report["trust"] = _check_trust_layer()

    try:
        health = _fetch_health(health_url)
        report["health_status"] = health.get("status")
        staging = health.get("staging") or {}
        report["staging"] = staging
        _check_staging_health(staging, issues, warnings)
        report["pipeline_hint"] = health.get("pipeline") or {}
        report["desk"] = health.get("desk") or {}

        rt = staging.get("runtime") or {}
        if rt.get("git_sha") and rt.get("git_sha") != "unknown":
            if report["git_head"] != "unknown" and not str(rt["git_sha"]).startswith(str(report["git_head"])):
                warnings.append(f"git_sha mismatch env={rt.get('git_sha')} repo={report['git_head']}")
    except urllib.error.URLError as exc:
        issues.append(f"health unreachable: {exc}")
    except Exception as exc:
        issues.append(f"health parse failed: {exc}")

    report["issues"] = issues
    report["warnings"] = warnings
    verdict = "GO"
    if issues:
        verdict = "NO-GO"
    elif warnings and strict:
        verdict = "NO-GO"
    report["verdict"] = verdict

    print(json.dumps(report, indent=2, default=str))
    print(f"\nVERDICT: {verdict}")
    if issues:
        print("Issues:")
        for i in issues:
            print(f"  - {i}")
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  - {w}")
    return 0 if verdict == "GO" else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Final staging GO/NO-GO validator")
    p.add_argument("--health-url", default=os.getenv("HEALTH_URL", "http://127.0.0.1:8080/health"))
    p.add_argument("--strict", action="store_true", help="Treat warnings as NO-GO")
    args = p.parse_args()
    return run_validator(health_url=args.health_url, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
