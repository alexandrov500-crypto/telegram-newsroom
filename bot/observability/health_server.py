from __future__ import annotations

import asyncio
from typing import Any

from bot.observability.logging_setup import get_logger
from bot.observability.registry import ObservabilityRegistry

logger = get_logger(__name__)


def create_health_app(
    registry: ObservabilityRegistry,
    *,
    db_path: str | None = None,
    ops_platform: Any | None = None,
    startup_report: Any | None = None,
) -> Any:
    from fastapi import FastAPI, Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    app = FastAPI(title="Newsroom Health", docs_url=None, redoc_url=None)
    app.state.registry = registry
    app.state.startup_report = startup_report

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "telegram-newsroom"}

    @app.get("/ready")
    async def ready() -> dict[str, object]:
        snap = await registry.snapshot()
        status = "ok"
        if registry.queue_backlog() > 0 and not registry.scheduler_running:
            status = "degraded"
        body = {"status": status, **snap}
        return body

    @app.get("/self-check")
    async def self_check() -> dict[str, object]:
        report = app.state.startup_report
        if report is None:
            from bot.operations.startup_validation import StartupValidationRunner

            report = StartupValidationRunner.run_smoke()
            app.state.startup_report = report
        failed = [c.check_id for c in report.checks if not c.passed]
        return {
            "status": "ok" if report.passed else "degraded",
            "fingerprint": report.fingerprint,
            "checks": [c.to_dict() for c in report.checks],
            "failed": failed,
        }

    @app.get("/startup")
    async def startup_validation() -> dict[str, object]:
        """Full startup validation report (deterministic check list)."""
        report = app.state.startup_report
        if report is None:
            from bot.operations.startup_validation import StartupValidationRunner

            report = StartupValidationRunner.run_smoke()
            app.state.startup_report = report
        return report.to_dict()

    @app.get("/metrics")
    async def metrics() -> Response:
        payload = generate_latest()
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    @app.get("/safety")
    async def production_safety_snapshot() -> dict[str, object]:
        from bot.production_safety.context_holder import get_production_safety

        ps = get_production_safety()
        if ps is None:
            return {"status": "unavailable"}
        snap = await ps.tick(queue_depth=registry.queue_backlog())
        return {"status": "ok", **snap.to_dict()}

    @app.get("/reliability")
    async def reliability_snapshot() -> dict[str, object]:
        from bot.reliability.context_holder import get_reliability

        rel = get_reliability()
        if rel is None or rel.health.last_snapshot is None:
            return {"status": "unavailable"}
        snap = rel.health.last_snapshot
        return {"status": "ok", **snap.to_dict()}

    @app.get("/live_ops")
    async def live_ops_snapshot() -> dict[str, object]:
        from bot.live_ops.context_holder import get_live_ops

        lo = get_live_ops()
        if lo is None:
            return {"status": "unavailable"}
        snap = await lo.tick(queue_depth=registry.queue_backlog())
        return {
            "status": "ok",
            **snap.to_dict(),
            "event_bus": lo.event_bus.snapshot(),
            "go_live": lo.go_live_readiness(queue_depth=registry.queue_backlog()),
        }

    @app.get("/evolution")
    async def ops_evolution_snapshot() -> dict[str, object]:
        from bot.ops_evolution.context_holder import get_ops_evolution

        ev = get_ops_evolution()
        if ev is None:
            return {"status": "unavailable"}
        tick = await ev.tick()
        return {
            "status": "ok",
            **tick,
            "report": ev.evolution_report_text(),
        }

    @app.get("/week1")
    async def week1_snapshot() -> dict[str, object]:
        from bot.week1.context_holder import get_week1

        w1 = get_week1()
        if w1 is None:
            return {"status": "unavailable"}
        tick = await w1.tick()
        return {"status": "ok", **tick, "baselines": w1.baseline.status_html()}

    @app.get("/week1")
    async def week1_snapshot() -> dict[str, object]:
        from bot.week1.context_holder import get_week1

        w1 = get_week1()
        if w1 is None:
            return {"status": "unavailable"}
        tick = await w1.tick()
        return {"status": "ok", **tick, "baselines": w1.baseline.status_html()}

    @app.get("/operational_memory")
    async def operational_memory_snapshot() -> dict[str, object]:
        from bot.operational_memory.context_holder import get_opmem

        op = get_opmem()
        if op is None:
            return {"status": "unavailable"}
        tick = await op.tick()
        return {"status": "ok", **tick, **op.snapshot()}

    @app.get("/predictive_risk")
    async def predictive_risk_snapshot() -> dict[str, object]:
        from bot.operational_memory.context_holder import get_opmem

        op = get_opmem()
        if op is None:
            return {"status": "unavailable"}
        return {"status": "ok", "predictions": op.repository.latest_predictions()}

    @app.get("/incident_patterns")
    async def incident_patterns_snapshot() -> dict[str, object]:
        from bot.operational_memory.context_holder import get_opmem

        op = get_opmem()
        if op is None:
            return {"status": "unavailable"}
        return {
            "status": "ok",
            "recurrent": op.repository.recurrent_types(min_count=2),
            "fingerprints": op.repository.list_fingerprints(limit=20),
        }

    @app.get("/drift_state")
    async def drift_state_snapshot() -> dict[str, object]:
        from bot.operational_memory.context_holder import get_opmem

        op = get_opmem()
        if op is None:
            return {"status": "unavailable"}
        return {"status": "ok", "drift": op.repository.latest_drift()}

    @app.get("/seasonality")
    async def seasonality_snapshot() -> dict[str, object]:
        from bot.operational_memory.context_holder import get_opmem

        op = get_opmem()
        if op is None:
            return {"status": "unavailable"}
        key = op.seasonality.bucket_key()
        profile = op.repository.get_seasonality(key)
        return {"status": "ok", "bucket": key, "profile": profile}

    @app.get("/live_status")
    async def live_status_snapshot() -> dict[str, object]:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is None:
            return {"status": "unavailable"}
        tick = await cl.tick()
        return {"status": "ok", **tick, **cl.snapshot()}

    @app.get("/channel_health")
    async def channel_health_snapshot() -> dict[str, object]:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is None:
            return {"status": "unavailable"}
        return {"status": "ok", **cl.snapshot()}

    @app.get("/runtime_identity")
    async def runtime_identity_endpoint() -> dict[str, object]:
        from bot.runtime.instance import runtime_identity_snapshot

        return runtime_identity_snapshot()

    @app.get("/observation_pulse")
    async def observation_pulse() -> dict[str, object]:
        """Latest operational observation metrics (48h phase)."""
        from bot.ops_observation.collector import collect_observation_pulse

        return collect_observation_pulse()

    @app.get("/trust_calibration")
    async def trust_calibration_endpoint() -> dict[str, object]:
        """Subsystem reliability, warning precision, operator agreement trends."""
        from pathlib import Path

        from bot.trust_calibration.service import trust_calibration_payload
        from bot.storage.db import default_db_path

        path = Path(db_path) if db_path else default_db_path()
        return trust_calibration_payload(db_path=path)

    @app.get("/ops_consolidation")
    async def ops_consolidation_endpoint() -> dict[str, object]:
        """Architecture audit: contracts, complexity, signal overlap, operator surface."""
        from pathlib import Path

        from bot.ops_consolidation.service import consolidation_payload
        from bot.storage.db import default_db_path

        path = Path(db_path) if db_path else default_db_path()
        return consolidation_payload(db_path=path)

    @app.get("/ops_resilience")
    async def ops_resilience_endpoint() -> dict[str, object]:
        """Operational posture, dependency health, backpressure, recovery guidance."""
        from pathlib import Path

        from bot.ops_resilience.service import resilience_status_payload
        from bot.storage.db import default_db_path

        path = Path(db_path) if db_path else default_db_path()
        return resilience_status_payload(db_path=path)

    @app.get("/weekly_review")
    async def weekly_review_endpoint() -> dict[str, object]:
        """Weekly operational evidence review — signal usefulness and tuning guidance."""
        from pathlib import Path

        from bot.ops_evidence.service import weekly_review_payload
        from bot.storage.db import default_db_path

        path = Path(db_path) if db_path else default_db_path()
        payload = weekly_review_payload(db_path=path)
        return {"status": "ok", **payload}

    @app.get("/ops_storage")
    async def ops_storage_endpoint() -> dict[str, object]:
        """Database health, retention status, archive pressure, entropy metrics."""
        from pathlib import Path

        from bot.ops_lifecycle.storage_report import build_ops_storage_payload
        from bot.storage.db import default_db_path

        path = Path(db_path) if db_path else default_db_path()
        return build_ops_storage_payload(path)

    @app.get("/priority_queue")
    async def priority_queue_endpoint(limit: int = 20) -> dict[str, object]:
        """Ranked pending-news queue with explainable editorial priority."""
        from pathlib import Path

        from bot.editorial.priority.service import priority_queue_payload
        from bot.storage.db import default_db_path

        path = Path(db_path) if db_path else default_db_path()
        return priority_queue_payload(limit=min(limit, 50), db_path=path)

    @app.get("/storyline/{storyline_id}")
    async def storyline_timeline(storyline_id: str) -> dict[str, object]:
        """Editorial storyline chronology and narrative state (advisory memory)."""
        from pathlib import Path

        from bot.editorial.memory.service import get_editorial_memory_repo
        from bot.storage.db import default_db_path

        path = Path(db_path) if db_path else default_db_path()
        repo = get_editorial_memory_repo(path)
        payload = repo.storyline_timeline_payload(storyline_id)
        if payload is None:
            return {"status": "not_found", "storyline_id": storyline_id}
        return {"status": "ok", **payload}

    @app.get("/incident_timeline")
    async def incident_timeline(
        since: str | None = None,
        until: str | None = None,
        event_type: str | None = None,
        correlation_id: str | None = None,
        publish_id: str | None = None,
        limit: int = 500,
    ) -> dict[str, object]:
        from bot.ops_forensics.repository import ForensicsRepository

        events = ForensicsRepository().query_timeline(
            since=since,
            until=until,
            event_type=event_type,
            correlation_id=correlation_id,
            publish_id=publish_id,
            limit=min(limit, 2000),
        )
        return {"status": "ok", "count": len(events), "events": events}

    @app.get("/operational_audit")
    async def operational_audit(
        publish_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        from bot.ops_forensics.repository import ForensicsRepository

        entries = ForensicsRepository().query_audit(
            publish_id=publish_id,
            correlation_id=correlation_id,
            limit=min(limit, 1000),
        )
        return {"status": "ok", "count": len(entries), "entries": entries}

    @app.get("/runtime_loops")
    async def runtime_loops_snapshot() -> dict[str, object]:
        from bot.observability.loop_registry import get_loop_registry
        from bot.runtime.profile import get_runtime_capabilities

        caps = get_runtime_capabilities()
        reg = get_loop_registry()
        view = reg.runtime_loops_view(caps)
        stalled = reg.watchdog_stalled_names(caps=caps)
        return {
            "status": "ok",
            **view,
            "stalled": stalled,
        }

    @app.get("/runtime_performance")
    async def runtime_performance_snapshot() -> dict[str, object]:
        from bot.observability.loop_diagnostics import collect_lag_context, snapshot
        from bot.runtime.profile import get_runtime_capabilities

        caps = get_runtime_capabilities()
        return {
            "status": "ok",
            "runtime_profile": caps.profile.value,
            **snapshot(),
            "context": collect_lag_context(),
        }

    @app.get("/recent_incidents")
    async def recent_incidents_snapshot() -> dict[str, object]:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is None:
            return {"status": "unavailable"}
        return {"status": "ok", "incidents": cl.repository.recent_incidents(limit=20)}

    @app.get("/live_feedback")
    async def live_feedback_snapshot() -> dict[str, object]:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is None:
            return {"status": "unavailable"}
        return {"status": "ok", "scores": cl.feedback.scores()}

    @app.get("/pilot_readiness")
    async def pilot_readiness() -> dict[str, object]:
        from pathlib import Path

        from bot.live_ops.pilot_readiness import (
            evaluate_pilot_db,
            evaluate_pilot_env,
            persistence_snapshot,
        )
        from bot.storage.db import default_db_path, init_database

        env = evaluate_pilot_env()
        db_path = default_db_path()
        init_database(db_path)
        db = evaluate_pilot_db(db_path)
        ready = env.ready and db.ready
        return {
            "status": "ok" if ready else "degraded",
            "ready": ready,
            "env": env.to_dict(),
            "db": db.to_dict(),
            "persistence": persistence_snapshot(db_path),
        }

    @app.get("/live_metrics_timeline")
    async def live_metrics_timeline() -> dict[str, object]:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is None:
            return {"status": "unavailable"}
        return {"status": "ok", "timeline": cl.metrics.timeline(limit=48)}

    @app.get("/publish_trace/{pending_news_id}")
    async def publish_trace_detail(pending_news_id: int) -> dict[str, object]:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is None:
            return {"status": "unavailable"}
        trace = cl.publish_trace.get(pending_news_id)
        if not trace:
            return {"status": "not_found"}
        return {"status": "ok", "trace": trace}

    @app.get("/publishing_safety")
    async def publishing_safety_snapshot() -> dict[str, object]:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is None:
            return {"status": "unavailable"}
        state = cl.repository.get_state() or {}
        return {
            "status": "ok",
            "paused": bool(state.get("paused")),
            "frozen": bool(state.get("frozen")),
            "live_mode": state.get("live_mode"),
            "success_rate": cl.repository.publish_success_rate(),
        }

    @app.get("/live_deploy")
    async def live_deploy_snapshot() -> dict[str, object]:
        from bot.live_deploy.context_holder import get_live_deploy

        ld = get_live_deploy()
        if ld is None:
            return {"status": "unavailable"}
        tick = await ld.tick()
        return {
            "status": "ok",
            **tick,
            "first_72h": ld.first_72h.status_html(),
        }

    @app.get("/ops_playbook")
    async def ops_playbook_snapshot() -> dict[str, object]:
        from bot.ops_playbook.context_holder import get_ops_playbook

        pb = get_ops_playbook()
        if pb is None:
            return {"status": "unavailable"}
        tick = await pb.tick()
        return {
            "status": "ok",
            **tick,
            "launch_period": pb.launch_period.status_html(),
        }

    @app.get("/go_live")
    async def go_live_snapshot() -> dict[str, object]:
        from bot.go_live.context_holder import get_go_live

        gl = get_go_live()
        if gl is None:
            return {"status": "unavailable"}
        r = gl._last_activation
        return {
            "status": "ok" if r and r.passed else "degraded",
            "activation": r.structured() if r else None,
            "publication_stage": gl.first_publication.current().value,
            "rollout": gl.first_publication.rollout_for(),
        }

    @app.get("/platform")
    async def platform_snapshot() -> dict[str, object]:
        from bot.platform.context_holder import get_platform

        plat = get_platform()
        if plat is None:
            return {"status": "unavailable"}
        tick = await plat.tick()
        snap = plat._last_snapshot or {}
        return {
            "status": "ok",
            **tick,
            "snapshot": snap,
            "health": plat.platform_health_text(),
        }

    @app.get("/post_ga")
    async def post_ga_snapshot() -> dict[str, object]:
        from bot.post_ga.context_holder import get_post_ga

        pg = get_post_ga()
        if pg is None:
            return {"status": "unavailable"}
        tick = await pg.tick()
        return {"status": "ok", **tick, "live_exec": pg.live_exec_text()}

    @app.get("/ga")
    async def ga_ops_snapshot() -> dict[str, object]:
        from bot.ga_ops.context_holder import get_ga_ops

        ga = get_ga_ops()
        if ga is None:
            return {"status": "unavailable"}
        tick = await ga.tick()
        return {"status": "ok", **tick}

    @app.get("/rc1")
    async def rc1_snapshot() -> dict[str, object]:
        from bot.rc1.context_holder import get_rc1

        rc = get_rc1()
        if rc is None:
            return {"status": "unavailable"}
        tick = await rc.tick()
        return {
            "status": "ok",
            "build": rc.lockdown.build_id,
            **tick,
            "dashboard": rc.launch_dashboard_text(),
        }

    @app.get("/certification")
    async def ops_certification_snapshot() -> dict[str, object]:
        from bot.ops_certification.context_holder import get_ops_certification

        oc = get_ops_certification()
        if oc is None:
            return {"status": "unavailable"}
        tick = await oc.tick()
        return {"status": "ok", **tick}

    @app.get("/operational_readiness")
    async def operational_readiness() -> dict[str, object]:
        if ops_platform is None:
            return {"status": "unavailable", "overall": 0.0}
        row = ops_platform.repository.latest_readiness_score()
        if not row:
            return {"status": "unknown", "overall": 0.0}
        import json

        detail: dict = {}
        try:
            detail = json.loads(row.get("detail_json") or "{}")
        except json.JSONDecodeError:
            pass
        overall = float(row.get("staging_score", 0))
        return {
            "status": "ok" if overall >= 0.82 else "degraded" if overall >= 0.55 else "critical",
            "overall": overall,
            "components": detail.get("components", {}),
            "blockers": detail.get("blockers", []),
            "certification_passed": bool(row.get("certification_passed")),
            "burnin_health": float(row.get("burnin_health", 0)),
            "epistemic_stability": float(row.get("epistemic_stability", 0)),
        }

    if db_path:
        from bot.operations.ops_explorer import mount_ops_routes

        mount_ops_routes(app, db_path=db_path, ops_platform=ops_platform)

    return app


async def serve_health_http(
    registry: ObservabilityRegistry,
    *,
    host: str,
    port: int,
    db_path: str | None = None,
    ops_platform: Any | None = None,
    startup_report: Any | None = None,
) -> asyncio.Task[None]:
    """Run uvicorn in background. Returns the server task."""
    import uvicorn

    app = create_health_app(
        registry,
        db_path=db_path,
        ops_platform=ops_platform,
        startup_report=startup_report,
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    async def _run() -> None:
        logger.info("event=health_server_started", host=host, port=port)
        await server.serve()

    task = asyncio.create_task(_run(), name="health-http")
    return task
