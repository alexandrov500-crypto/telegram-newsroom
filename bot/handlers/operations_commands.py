from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router

if TYPE_CHECKING:
    from bot.operations.runtime import OperationsPlatform


def register_operations_handlers(*, operations_platform: OperationsPlatform | None) -> None:
    @router.message(Command("staging_status"))
    @admin_only("/staging_status")
    async def cmd_staging_status(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        from bot.config import load_settings
        from bot.operations.startup_validation import StartupValidationRunner

        settings = load_settings()
        report = StartupValidationRunner.run(
            settings=settings,
            db_path=operations_platform.db_path,
            rss_feed_count=len(settings.rss_feed_list),
            operations_platform=operations_platform,
        )
        await message.answer(report.operator_summary()[:3900])

    @router.message(Command("ops"))
    @admin_only("/ops")
    async def cmd_ops(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations platform unavailable.")
            return
        burnin = operations_platform.repository.active_burnin()
        cert = operations_platform.repository.latest_certification()
        lines = [
            "Operations platform",
            f"  burn-in: {burnin['run_id'] if burnin else 'none'} ({burnin.get('profile') if burnin else '-'})",
            f"  certification: {cert['status'] if cert else 'not run'}",
        ]
        lines.append(operations_platform.editorial_review.usefulness_report())
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("triage"))
    @admin_only("/triage")
    async def cmd_triage(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        alerts = operations_platform.ergonomics.triage_open()
        text = operations_platform.ergonomics.explainability_summary(alerts)
        await message.answer(text[:3900])

    @router.message(Command("review"))
    @admin_only("/review")
    async def cmd_review(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        parts = (message.text or "").split(maxsplit=3)
        if len(parts) < 4:
            await message.answer("Usage: /review <type> <target_id> <score_0_1> [note]")
            return
        try:
            score = float(parts[3])
        except ValueError:
            await message.answer("Invalid score.")
            return
        operations_platform.editorial_review.submit_review(
            parts[1],
            parts[2],
            score=score,
            useful=score >= 0.6,
            annotation=parts[4] if len(parts) > 4 else None,
            operator_id=str(message.from_user.id),
        )
        await message.answer(f"Review recorded for {parts[1]}:{parts[2]}")

    @router.message(Command("session"))
    @admin_only("/session")
    async def cmd_session(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 2 or parts[1] not in ("start", "end"):
            await message.answer("Usage: /session start <triage|review|contradiction> | /session end <session_id>")
            return
        if parts[1] == "start":
            stype = parts[2] if len(parts) > 2 else "triage"
            sid = operations_platform.operator_workflows.start_session(
                stype,
                operator_id=str(message.from_user.id),
            )
            await message.answer(f"Session started: {sid} ({stype})")
            return
        sid = parts[2] if len(parts) > 2 else ""
        metrics = operations_platform.operator_workflows.end_session(sid)
        if metrics is None:
            await message.answer("Unknown session.")
            return
        await message.answer(
            f"Session {metrics.session_id} ended: {metrics.actions} actions, fatigue={metrics.fatigue_score:.2f}"
        )

    @router.message(Command("incident"))
    @admin_only("/incident")
    async def cmd_incident(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /incident <key>")
            return
        from pathlib import Path

        export = operations_platform.incident_ops.export_bundle(
            parts[1],
            timeline=[{"event": "operator_export", "operator": str(message.from_user.id)}],
            export_dir=Path("var/incidents"),
        )
        text = f"Incident bundle {export.bundle_id}\n{export.path}\n{export.rca_summary[:800]}"
        await message.answer(text[:3900])

    @router.message(Command("dashboard"))
    @admin_only("/dashboard")
    async def cmd_dashboard(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        dash = operations_platform.simplification.consolidate_dashboard()
        esc = operations_platform.simplification.escalation_summary()
        readiness = operations_platform.repository.latest_readiness_score()
        lines = [
            dash.summary,
            "",
            f"Open alerts: {dash.open_alerts}",
            f"Categories: {dash.top_categories}",
            "",
            esc,
        ]
        if readiness:
            lines.append(f"\nStaging score: {readiness['staging_score']:.2f}")
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("contradictions_queue"))
    @admin_only("/contradictions_queue")
    async def cmd_contradictions_queue(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        items = operations_platform.operator_workflows.contradiction_triage_queue()
        if not items:
            await message.answer("No open contradictions.")
            return
        lines = ["Contradiction triage:"]
        for c in items[:10]:
            lines.append(f"- {c['contradiction_id']}: {c.get('explanation', '')[:80]}")
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("incidents"))
    @admin_only("/incidents")
    async def cmd_incidents(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        rows = operations_platform.incidents.list_open()
        await message.answer(operations_platform.incidents.format_incident_list(rows)[:3900])

    @router.message(Command("incident_ack"))
    @admin_only("/incident_ack")
    async def cmd_incident_ack(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /incident_ack <incident_id>")
            return
        ok = operations_platform.incidents.acknowledge(
            parts[1].strip(),
            operator_id=str(message.from_user.id),
        )
        await message.answer("Acknowledged." if ok else "Incident not found.")

    @router.message(Command("incident_resolve"))
    @admin_only("/incident_resolve")
    async def cmd_incident_resolve(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /incident_resolve <incident_id> [note]")
            return
        tokens = parts[1].split(maxsplit=1)
        iid = tokens[0]
        note = tokens[1] if len(tokens) > 1 else ""
        ok = operations_platform.incidents.resolve(
            iid,
            operator_id=str(message.from_user.id),
            note=note,
        )
        await message.answer("Resolved." if ok else "Incident not found.")

    @router.message(Command("incident_export"))
    @admin_only("/incident_export")
    async def cmd_incident_export(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /incident_export <incident_id>")
            return
        bundle_id = operations_platform.incidents.export_bundle(parts[1].strip())
        if bundle_id is None:
            await message.answer("Incident not found.")
            return
        await message.answer(f"Exported archaeology bundle: <code>{bundle_id}</code>", parse_mode="HTML")

    @router.message(Command("operational_readiness"))
    @admin_only("/operational_readiness")
    async def cmd_operational_readiness(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        from bot.operations.operational_readiness import compute_operational_readiness

        readiness = operations_platform.repository.latest_readiness_score()
        if readiness and readiness.get("detail_json"):
            import json

            try:
                detail = json.loads(readiness["detail_json"])
                components = detail.get("components", {})
                blockers = detail.get("blockers", [])
            except json.JSONDecodeError:
                components, blockers = {}, []
            score = float(readiness["staging_score"])
            from bot.operations.operational_readiness import OperationalReadinessScore

            text = OperationalReadinessScore(
                overall=score,
                trend="stable",
                components=components,
                blockers=blockers,
            ).summary_text()
        else:
            text = compute_operational_readiness(signals={}, ops_report={}).summary_text()
        await message.answer(text[:3900])

    @router.message(Command("feeds"))
    @admin_only("/feeds")
    async def cmd_feeds(message: Message) -> None:
        if operations_platform is None:
            await message.answer("Operations unavailable.")
            return
        report = operations_platform.repository.feed_health_report()
        if not report:
            results = operations_platform.feed_validation.validate_catalog()
            lines = ["Feed validation:"]
            for r in results[:12]:
                lines.append(f"- {r.source_name}: {r.reliability:.2f} ({r.items_fetched} items)")
        else:
            lines = ["Feed health:"]
            for r in report[:12]:
                lines.append(f"- {r.get('source_name') or r['feed_url'][:40]}: {r['reliability_score']:.2f}")
        await message.answer("\n".join(lines)[:3900])
