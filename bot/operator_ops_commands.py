"""Operator read-only ops commands + autopublish pause/resume."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from bot.admin_handlers import _admin_private_message
from utils.database_url import sqlite_path_from_url

router = Router(name="operator_ops")


@router.message(Command("runtime"))
async def cmd_runtime(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.observability.runtime_protection import protection_payload
    from app.observability.runtime_health import collect_health_snapshot

    snap = collect_health_snapshot(settings=settings)
    prot = protection_payload(settings.runtime_state_dir)
    await message.answer(
        f"protection={prot.get('current_state')}\n"
        f"activations={prot.get('protection_activation_count')}\n"
        f"recoveries={prot.get('recovery_count')}\n"
        f"rss_mb={snap.get('rss_mb')} drift={snap.get('rss_drift_mb')}\n"
        f"flags={','.join(snap.get('degradation_flags') or [])}",
        disable_web_page_preview=True,
    )


@router.message(Command("anomalies"))
async def cmd_anomalies(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    eg_path = Path(settings.runtime_state_dir) / "execution_graph_report.json"
    safety_path = Path(settings.runtime_state_dir) / "execution_graph_safety.json"
    lines = ["Execution graph anomalies:"]
    if eg_path.is_file():
        data = json.loads(eg_path.read_text(encoding="utf-8"))
        lines.append(
            f"critical_ticks={data.get('critical_tick_count')} "
            f"warnings={data.get('warning_tick_count')} "
            f"consistency={data.get('consistency_rate')}"
        )
    else:
        lines.append("(no execution_graph_report.json — run make execution-graph-report)")
    if safety_path.is_file():
        safety = json.loads(safety_path.read_text(encoding="utf-8"))
        lines.append(f"corrupted_ticks={len(safety.get('corrupted_ticks') or {})}")
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@router.message(Command("lastpub"))
async def cmd_lastpub(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path or not Path(path).is_file():
        await message.answer("DB unavailable.")
        return
    conn = sqlite3.connect(path, timeout=5.0)
    row = conn.execute(
        """
        SELECT pp.published_at, pp.telegram_post_id, d.id
        FROM published_posts pp
        JOIN drafts d ON d.id = pp.draft_id
        ORDER BY pp.id DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    if not row:
        await message.answer("No publishes yet.")
        return
    await message.answer(
        f"draft_id={row[2]} telegram_post_id={row[1]}\npublished_at={row[0]}",
        disable_web_page_preview=True,
    )


@router.message(Command("growth_pulse"))
async def cmd_growth_pulse(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.growth.autonomous_robot import collect_growth_pulse, format_pulse_telegram

    pulse = await collect_growth_pulse(
        runtime_dir=settings.runtime_state_dir,
        channel_id=int(settings.target_channel_id),
    )
    await message.answer(format_pulse_telegram(pulse), disable_web_page_preview=True)


@router.message(Command("pause_autopublish"))
async def cmd_pause_autopublish(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.observability.publish_continuity import set_operator_autopublish_pause

    set_operator_autopublish_pause(settings.runtime_state_dir, paused=True, operator_id=message.from_user.id)
    await message.answer("Autonomous publish PAUSED (operator). Ingest/diagnostics continue.")


@router.message(Command("resume_autopublish"))
async def cmd_resume_autopublish(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.observability.publish_continuity import set_operator_autopublish_pause

    set_operator_autopublish_pause(settings.runtime_state_dir, paused=False, operator_id=message.from_user.id)
    try:
        from app.ops.public_incident_safety import clear_incident_freeze

        clear_incident_freeze(settings.runtime_state_dir, operator_id=int(message.from_user.id))
    except Exception:
        pass
    try:
        from app.ops.live_rollback import deactivate_live_rollback

        deactivate_live_rollback(settings.runtime_state_dir, operator_id=int(message.from_user.id))
    except Exception:
        pass
    await message.answer("Autonomous publish RESUMED (operator). Gates still apply.")


def _mobile_block(title: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    if len(body) > 3800:
        body = body[:3800] + "\n…"
    return f"{title}\n{body}"


def _sev(ok: bool, *, warn: bool = False) -> str:
    if ok:
        return "🟢"
    return "🟠" if warn else "🔴"


def _contract_status(runtime_dir: str) -> dict[str, object]:
    path = Path(runtime_dir) / "final_release_readiness_report.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    path = Path(runtime_dir) / "final_public_check_report.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "FINAL_RELEASE_READINESS_VERDICT": data.get("RELEASE_CONTRACT_VERDICT"),
                    "blockers": data.get("blockers") or [],
                    "warnings": data.get("warnings") or [],
                }
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "FINAL_RELEASE_READINESS_VERDICT": "NOT_READY",
        "blockers": ["no_final_check_report"],
        "warnings": [],
    }


def _verdict_label(verdict: str) -> tuple[str, str]:
    v = str(verdict or "NOT_READY").upper()
    if v == "READY_FOR_PUBLIC":
        return "READY", "🟢"
    if v == "CONDITIONAL":
        return "CONDITIONAL", "🟠"
    return "NOT READY", "🔴"


@router.message(Command("release_status"))
async def cmd_release_status(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.ops.controlled_rollout import controlled_rollout_enabled, current_rollout_stage, rollout_stage_config
    from app.observability.prepublic_qa import prepublic_qa_enabled
    contract = _contract_status(settings.runtime_state_dir)
    label, icon = _verdict_label(str(contract.get("FINAL_RELEASE_READINESS_VERDICT") or "NOT_READY"))
    cfg = rollout_stage_config()
    lines = [
        f"{_sev(controlled_rollout_enabled(), warn=True)} rollout={controlled_rollout_enabled()} stage={current_rollout_stage().value}",
        f"⚙️ max_pub/h={cfg.max_publishes_per_hour} auto={cfg.auto_publish_allowed}",
        f"🧪 qa_mirror={cfg.qa_mirror} PREPUBLIC_QA={prepublic_qa_enabled()}",
        f"{icon} readiness={label}",
    ]
    for b in (contract.get("blockers") or [])[:3]:
        lines.append(f"• {b}")
    await message.answer(_mobile_block("Release", lines), disable_web_page_preview=True)


@router.message(Command("burnin_status"))
async def cmd_burnin_status(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.observability.burnin_validation import load_burnin_validation

    data = load_burnin_validation(settings.runtime_state_dir)
    lines = [
        f"BURNIN_VERDICT={data.get('BURNIN_VERDICT', 'unknown')}",
        f"continuity={data.get('continuity', {}).get('autonomous_continuity_score')}",
        f"publishes_24h={data.get('publishes_24h')}",
        f"uptime_sec={data.get('uptime_sec')}",
    ]
    await message.answer(_mobile_block("Burn-in", lines), disable_web_page_preview=True)


@router.message(Command("runtime_state"))
async def cmd_runtime_state(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.observability.runtime_protection import protection_payload
    from app.ops.public_incident_safety import incident_payload
    from app.observability.publish_continuity import compute_autonomous_continuity_score
    from app.runtime_activity import activity_snapshot

    contract = _contract_status(settings.runtime_state_dir)
    label, icon = _verdict_label(str(contract.get("FINAL_RELEASE_READINESS_VERDICT") or "NOT_READY"))
    prot = protection_payload(settings.runtime_state_dir)
    inc = incident_payload(settings.runtime_state_dir)
    act = activity_snapshot()
    critical = str(prot.get("current_state") or "").lower() == "critical"
    raw = os.getenv("DATABASE_URL", settings.database_url).strip()
    dbp = sqlite_path_from_url(raw)
    cont_score = None
    if dbp and Path(dbp).is_file():
        conn = sqlite3.connect(dbp, timeout=5.0)
        cont_score = compute_autonomous_continuity_score(conn, runtime_dir=settings.runtime_state_dir).get(
            "autonomous_continuity_score"
        )
        conn.close()
    lines = [
        f"{_sev(not critical)} protection={prot.get('current_state')}",
        f"🛡️ {','.join(prot.get('active_protections') or ['none'])[:120]}",
        f"🚧 incident_frozen={inc.get('frozen')} restart_guard={inc.get('restart_loop_guard_active')}",
        f"📰 last_publish={act.get('last_successful_publish_at')}",
        f"📈 health_score={cont_score if cont_score is not None else 'UNKNOWN'}",
        f"{icon} readiness={label}",
    ]
    for b in (contract.get("blockers") or [])[:3]:
        lines.append(f"• {b}")
    await message.answer(_mobile_block("Runtime", lines), disable_web_page_preview=True)


@router.message(Command("last_alerts"))
async def cmd_last_alerts(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    path = Path(settings.runtime_state_dir) / "ops" / "pending_notifications.jsonl"
    if not path.is_file():
        await message.answer("No pending alerts file.")
        return
    rows = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-5:]
    lines: list[str] = []
    for ln in rows:
        try:
            o = json.loads(ln)
            lines.append(f"{o.get('severity','?')}: {str(o.get('message') or o.get('kind',''))[:80]}")
        except json.JSONDecodeError:
            lines.append(ln[:80])
    await message.answer(_mobile_block("Alerts", lines or ["(empty)"]), disable_web_page_preview=True)


@router.message(Command("recent_failures"))
async def cmd_recent_failures(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    tg = Path(settings.runtime_state_dir) / "telegram_production_state.json"
    lines: list[str] = []
    if tg.is_file():
        st = json.loads(tg.read_text(encoding="utf-8"))
        lines.append(
            f"telegram_fail_streak={st.get('consecutive_api_failures')} "
            f"flood={st.get('flood_wait_total')} reconnect={st.get('reconnect_total')}"
        )
    log_path = Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log"))
    if log_path.is_file():
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
        hits = [ln for ln in tail if "publish failed" in ln.lower() or "telegram" in ln.lower()][-3:]
        lines.extend(hits or ["(no recent telegram/publish errors in log tail)"])
    await message.answer(_mobile_block("Failures", lines or ["(none)"]), disable_web_page_preview=True)


@router.message(Command("continuity"))
async def cmd_continuity(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from utils.database_url import sqlite_path_from_url
    from app.observability.publish_continuity import compute_autonomous_continuity_score, is_operator_autopublish_paused
    from app.ops.controlled_rollout import current_rollout_stage
    contract = _contract_status(settings.runtime_state_dir)
    label, icon = _verdict_label(str(contract.get("FINAL_RELEASE_READINESS_VERDICT") or "NOT_READY"))
    path = sqlite_path_from_url(os.getenv("DATABASE_URL", settings.database_url))
    if not path or not Path(path).is_file():
        await message.answer("DB unavailable.")
        return
    conn = sqlite3.connect(path, timeout=5.0)
    m = compute_autonomous_continuity_score(conn, runtime_dir=settings.runtime_state_dir)
    conn.close()
    score = m.get("autonomous_continuity_score")
    lines = [
        f"{_sev(float(score or 0) >= 55, warn=True)} score={score if score is not None else 'UNKNOWN'}",
        f"⏱️ gap_h={m.get('publish_gap_hours')} scheduler_active={m.get('scheduler_active')}",
        f"⏸️ operator_pause={is_operator_autopublish_paused(settings.runtime_state_dir)}",
        f"🚀 rollout_stage={current_rollout_stage().value}",
        f"{icon} readiness={label}",
    ]
    for b in (contract.get("blockers") or [])[:3]:
        lines.append(f"• {b}")
    await message.answer(_mobile_block("Continuity", lines), disable_web_page_preview=True)


@router.message(Command("go_status"))
async def cmd_go_status(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.observability.burnin_validation import load_burnin_validation

    contract = _contract_status(settings.runtime_state_dir)
    label, icon = _verdict_label(str(contract.get("FINAL_RELEASE_READINESS_VERDICT") or "NOT_READY"))
    burn = load_burnin_validation(settings.runtime_state_dir)
    lines = [
        f"{icon} verdict={label}",
        f"📈 BURNIN_VERDICT={burn.get('burnin_verdict') or burn.get('BURNIN_VERDICT', 'unknown')}",
        f"🚀 rollout_stage={os.getenv('ROLLOUT_STAGE', 'STAGE_0_PRIVATE_QA')}",
        f"📰 last_publish={__import__('app.runtime_activity', fromlist=['activity_snapshot']).activity_snapshot().get('last_successful_publish_at')}",
        f"⛔ blockers={len(contract.get('blockers') or [])}",
    ]
    for b in (contract.get("blockers") or [])[:3]:
        lines.append(f"• {b}")
    await message.answer(_mobile_block("GO status", lines), disable_web_page_preview=True)


@router.message(Command("final_check"))
async def cmd_final_check(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    contract = _contract_status(settings.runtime_state_dir)
    label, icon = _verdict_label(str(contract.get("FINAL_RELEASE_READINESS_VERDICT") or "NOT_READY"))
    pub = Path(settings.runtime_state_dir) / "final_public_check_report.json"
    rel = Path(settings.runtime_state_dir) / "final_release_readiness_report.json"
    lines = [
        f"{icon} contract={label}",
        f"📄 public_check={'yes' if pub.is_file() else 'no'}",
        f"📄 release_readiness={'yes' if rel.is_file() else 'no'}",
    ]
    for b in (contract.get("blockers") or [])[:3]:
        lines.append(f"• {b}")
    await message.answer(_mobile_block("Final check", lines), disable_web_page_preview=True)


@router.message(Command("rollback_status"))
async def cmd_rollback_status(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from app.ops.live_rollback import rollback_payload

    rb = rollback_payload(settings.runtime_state_dir)
    active = bool(rb.get("active"))
    lines = [
        f"{_sev(not active, warn=True)} LIVE_ROLLBACK_MODE={rb.get('enabled')}",
        f"rollback_active={active}",
        f"reason={str(rb.get('reason') or rb.get('last_reason') or 'n/a')[:80]}",
        f"duration_sec={rb.get('duration_sec') or rb.get('last_duration_sec') or 0}",
        "resume=/resume_autopublish",
    ]
    await message.answer(_mobile_block("Rollback", lines), disable_web_page_preview=True)
