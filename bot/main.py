from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env, load_settings
from bot.handlers import register_handlers
from bot.runtime.auth import configure_admin_access
from bot.runtime.state import runtime_state
from bot.analytics.scheduler import run_analytics_scheduler
from bot.digest.scheduler import run_digest_scheduler
from bot.digest.service import DigestService
from bot.ingestion.runner import run_ingestion_loop
from bot.ingestion.telegram import run_telegram_ingestion_loop
from bot.ingestion.telethon_client import TelethonSettings
from bot.editorial.agent_service import EditorialAgentService
from bot.editorial.story_memory import StoryMemoryService
from bot.distributed.config import (
    load_cluster_config,
    role_allows_digest,
    role_allows_ingest,
    role_allows_operator,
)
from bot.distributed.cluster.coordinator import ClusterCoordinator
from bot.runtime.autonomous_runtime import build_autonomous_runtime
from bot.cognitive.runtime import build_cognitive_runtime
from bot.mesh.runtime import build_federated_cognitive_mesh
from bot.epistemic.runtime import build_epistemic_integrity_layer
from bot.operations.runtime import build_operations_platform
from bot.distributed.stream.factory import create_stream_bus
from bot.distributed.federation.learning_sync import FederatedLearningSync
from bot.signals.editorial_agents import EditorialAgentRouter
from bot.signals.signal_service import SignalIntelligenceService
from bot.control_plane.service import ControlPlane
from bot.adaptive.service import AdaptiveOperationsService
from bot.storage.event_store import EventStore
from bot.storage.sourced_event_store import SourcedEventStore
from bot.publishing.idempotency import PublishIdempotencyStore
from bot.workflows.checkpoint_store import WorkflowCheckpointStore
from bot.workflows.recovery import WorkflowRecoveryService
from bot.storage.signal_repository import SignalRepository
from bot.storage.story_repository import StoryRepository
from bot.observability.alerts import AlertManager
from bot.observability.health_server import serve_health_http
from bot.observability.logging_setup import configure_structured_logging, get_logger
from bot.observability.metrics import set_active_jobs, set_queue_backlog
from bot.observability.openai_tracker import OpenAITracker
from bot.observability.registry import ObservabilityRegistry
from bot.observability.scheduler import run_openai_daily_aggregation_loop
from bot.observability.watchdog import BurnInWatchdog
from bot.storage.agent_repository import AgentRepository
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.entity_repository import EntityRepository
from bot.storage.observability_repository import ObservabilityRepository
from bot.storage.source_repository import SourceRepository
from bot.storage.telegram_seen_repository import TelegramSeenRepository
from bot.config import telethon_configured
from bot.publisher import ChannelPublisher
from bot.publishing.channel_router import ChannelRouter
from bot.storage.localization_repository import LocalizationRepository
from bot.storage.db import default_db_path, init_database
from bot.storage.cluster_repository import ClusterRepository
from bot.storage.coordination_factory import create_coordination_repository
from bot.storage.digest_repository import DigestRepository
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.repository import (
    ResilientLinkDedup,
    SeenLinkRepository,
    create_memory_link_dedup,
)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

logger = get_logger(__name__)


def _runtime_caps():
    from bot.runtime.profile import get_runtime_capabilities

    return get_runtime_capabilities()


async def _post_hourly_burnin_telegram(
    *,
    operations_platform,
    mesh_health: float,
    epistemic_detail: dict,
    result: dict,
) -> None:
    from bot.operator_console.context import get_operator_console
    from bot.operator_console.telemetry import build_burnin_telemetry_summary

    console = get_operator_console()
    if console is None:
        return
    amplification = float(result.get("replay_divergence", 0))
    summary = build_burnin_telemetry_summary(
        operations_platform=operations_platform,
        mesh_health=mesh_health,
        open_contradictions=int(epistemic_detail.get("open_contradictions", 0)),
        storage_growth_mb=float(result.get("storage_growth_mb", 0) or 0),
        amplification=amplification,
    )
    await console.notify_burnin_status(summary)


async def _post_epistemic_incidents_telegram(
    alerts: list,
    *,
    open_contradictions: int,
    operations_platform,
    mesh_health: float = 1.0,
) -> None:
    from bot.operator_console.context import get_operator_console

    console = get_operator_console()
    if console is None:
        return
    for alert in alerts[:3]:
        await console.notify_incident(
            kind="misinfo",
            title=f"Epistemic: {alert}",
            severity="warn",
            detail=f"Open contradictions: {open_contradictions}",
            suggested_action="Review /contradictions_queue",
            bundle_ref="ops:epistemic",
            mesh_health=mesh_health,
            open_contradictions=open_contradictions,
        )


async def _abort_staging_startup(
    bot: Bot,
    *,
    subsystem: str,
    settings,
    env_report=None,
    conn_report=None,
    startup_report=None,
    alerts: AlertManager | None = None,
    extra: dict | None = None,
) -> None:
    from bot.operations.startup_diagnostics import emit_startup_failure_diagnostics

    emit_startup_failure_diagnostics(
        subsystem=subsystem,
        settings=settings,
        env_report=env_report,
        conn_report=conn_report,
        startup_report=startup_report,
        extra=extra,
    )
    if settings.telegram_operator_chat_id:
        try:
            await bot.send_message(
                settings.telegram_operator_chat_id,
                f"⚠️ Staging startup aborted\nSubsystem: <b>{subsystem}</b>\n"
                "See process logs for remediation.",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("event=operator_abort_notify_failed")
    if alerts is not None:
        await alerts.critical(f"Staging startup aborted: {subsystem}")
    await bot.session.close()
    raise SystemExit(1)


async def run() -> None:
    bootstrap_env()
    settings = load_settings()
    configure_structured_logging(
        json_logs=settings.structured_logging,
        log_level="INFO",
        json_log_file=settings.log_json_file,
    )

    from bot.runtime.instance import create_runtime_identity, install_runtime_identity
    from bot.runtime.ownership import (
        RuntimeOwnershipError,
        acquire_runtime_ownership,
        release_runtime_ownership,
    )
    from bot.runtime.profile import get_runtime_capabilities

    _caps_boot = get_runtime_capabilities()
    _runtime_identity = install_runtime_identity(
        create_runtime_identity(_caps_boot.profile.value),
    )
    _ownership_lock = None
    try:
        _ownership_lock = acquire_runtime_ownership(_runtime_identity)
    except RuntimeOwnershipError as exc:
        holder = exc.holder
        logger.critical(
            "event=startup_aborted reason=runtime_ownership_conflict holder=%s",
            holder,
        )
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    logger.info("event=runtime_instance_started %s", _runtime_identity.log_line())
    import atexit

    atexit.register(release_runtime_ownership)

    registry = ObservabilityRegistry(
        scheduler_running=True,
        openai_available=bool(settings.openai_api_key),
    )

    print("Token loaded successfully")
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(),
    )

    from bot.live_ops.telegram_pilot import authenticate_bot_instance

    try:
        await authenticate_bot_instance(bot)
    except RuntimeError as exc:
        logger.critical("event=startup_aborted reason=telegram_auth %s", exc)
        await bot.session.close()
        raise SystemExit(f"Invalid BOT_TOKEN: {exc}") from exc

    if settings.is_staging and settings.staging_strict_startup:
        from bot.operations.staging_env_validation import validate_staging_environment

        env_report = validate_staging_environment(settings)
        if not env_report.passed:
            await _abort_staging_startup(
                bot,
                subsystem="environment",
                settings=settings,
                env_report=env_report,
            )

    alert_chat = settings.alert_chat_id or settings.telegram_operator_chat_id
    if alert_chat is None and settings.admin_user_id_set:
        alert_chat = next(iter(settings.admin_user_id_set))
    alerts = AlertManager(bot, alert_chat, cooldown_sec=settings.alert_cooldown_sec)

    from bot.operator_console import OperatorTelegramConsole, install_operator_console

    install_operator_console(OperatorTelegramConsole(bot, settings))

    if settings.is_staging:
        runtime_state.staging_mode = True
        runtime_state.shadow_publish_only = settings.shadow_publish_only or True
        runtime_state.auto_approval_enabled = False
        logger.info(
            "event=staging_mode_active shadow_publish=%s",
            runtime_state.shadow_publish_only,
        )

    publish_channel_id = settings.staging_publish_channel_id or settings.telegram_channel_id
    publisher = ChannelPublisher(bot, publish_channel_id)
    channel_router = ChannelRouter(
        publisher,
        settings.primary_channels,
        default_channel_id=publish_channel_id,
    )

    from bot.staging.telegram_connectivity import TelegramConnectivityCheck

    connectivity = TelegramConnectivityCheck(
        bot,
        digest_channel_id=settings.telegram_digest_channel_id or publish_channel_id,
        operator_chat_id=settings.telegram_operator_chat_id,
        publish_channel_id=publish_channel_id,
    )
    conn_report = await connectivity.run(strict=settings.staging_strict_startup)
    logger.info("event=telegram_connectivity\n%s", conn_report.operator_summary())
    if not conn_report.passed:
        if settings.telegram_operator_chat_id:
            try:
                await bot.send_message(
                    settings.telegram_operator_chat_id,
                    f"⚠️ Staging startup FAILED\n\n{conn_report.operator_summary()[:3500]}",
                )
            except Exception:
                logger.exception("event=operator_notify_failed")
        await alerts.warning(
            "Telegram staging connectivity failed",
            details={"summary": conn_report.operator_summary()},
        )
        if settings.is_staging and settings.staging_strict_startup:
            await _abort_staging_startup(
                bot,
                subsystem="telegram_connectivity",
                settings=settings,
                conn_report=conn_report,
                alerts=alerts,
            )

    if publish_channel_id is not None and conn_report.passed:
        verify = await publisher.send_to_channel(
            "[system] newsroom staging startup check",
            disable_notification=True,
        )
        if verify.success and verify.message_id is not None:
            try:
                await bot.delete_message(publish_channel_id, verify.message_id)
            except Exception:
                pass
            logger.info("event=startup_channel_verify_ok channel_id=%s", publish_channel_id)
        elif not verify.success:
            logger.error("event=startup_channel_verify_failed error=%s", verify.error)

    from bot.staging.feeds_config import resolve_staging_feed_urls

    if settings.is_staging:
        rss_feeds = resolve_staging_feed_urls(
            catalog_path=settings.staging_feeds_path,
            env_feeds=settings.rss_feed_list,
        )
    else:
        rss_feeds = settings.rss_feed_list
    if rss_feeds:
        logger.info("event=rss_configured", feed_count=len(rss_feeds), staging=settings.is_staging)
    else:
        logger.warning("event=rss_not_configured")

    from bot.staging.observability_validation import validate_startup_telemetry

    telemetry = validate_startup_telemetry(metrics_enabled=settings.metrics_enabled)
    logger.info("event=telemetry_validation\n%s", telemetry.summary())

    editorial: EditorialRepository | None = None
    clusters: ClusterRepository | None = None
    digest_service: DigestService | None = None
    telegram_seen: TelegramSeenRepository | None = None
    sources: SourceRepository | None = None
    entities: EntityRepository | None = None
    analytics: AnalyticsRepository | None = None
    agents: EditorialAgentService | None = None
    agent_repo: AgentRepository | None = None
    localizations: LocalizationRepository | None = None
    obs_repo: ObservabilityRepository | None = None
    openai_tracker: OpenAITracker | None = None
    story_memory: StoryMemoryService | None = None
    signal_intel: SignalIntelligenceService | None = None
    event_bus = None
    control_plane: ControlPlane | None = None
    adaptive: AdaptiveOperationsService | None = None
    cluster_coordinator: ClusterCoordinator | None = None
    cluster_scheduler = None
    autonomous_runtime = None
    cognitive_runtime = None
    cognitive_mesh = None
    epistemic_layer = None
    operations_platform = None
    reliability_coordinator = None
    production_safety = None
    live_ops_coordinator = None
    ops_certification_coordinator = None
    rc1_coordinator = None
    ga_ops_coordinator = None
    post_ga_coordinator = None
    ops_evolution_coordinator = None
    platform_coordinator = None
    ops_playbook_coordinator = None
    live_deploy_coordinator = None
    week1_coordinator = None
    opmem_coordinator = None
    controlled_live_coordinator = None
    go_live_coordinator = None
    federated_learning: FederatedLearningSync | None = None
    publish_idempotency: PublishIdempotencyStore | None = None
    workflow_recovery: WorkflowRecoveryService | None = None
    cluster_config = load_cluster_config()
    coordination = None

    ingestion_task = None
    digest_task = None
    telegram_task = None
    analytics_task = None
    health_task = None
    watchdog_task = None
    forensics_snapshot_task = None
    openai_agg_task = None
    story_maint_task = None
    cluster_metrics_task = None
    startup_report = None

    try:
        db_path = init_database(default_db_path())
        link_dedup: ResilientLinkDedup = ResilientLinkDedup(SeenLinkRepository(db_path))
        editorial = EditorialRepository(db_path)
        localizations = LocalizationRepository(db_path)
        sources = SourceRepository(db_path)
        entities = EntityRepository(db_path)
        analytics = AnalyticsRepository(db_path)
        agent_repo = AgentRepository(db_path)
        obs_repo = ObservabilityRepository(db_path)
        openai_tracker = OpenAITracker(
            obs_repo,
            cost_per_1k_input=settings.openai_cost_per_1k_input_usd,
            cost_per_1k_output=settings.openai_cost_per_1k_output_usd,
        )
        registry.set_queue_backlog_provider(obs_repo.count_pending_queue)
        clusters = ClusterRepository(
            db_path,
            similarity_threshold=settings.semantic_similarity_threshold,
        )
        coordination = create_coordination_repository(db_path)
        story_repo = StoryRepository(db_path)
        from bot.distributed.cluster.federation import FederatedStoryRegistry

        story_federation = FederatedStoryRegistry(
            coordination,
            node_id=cluster_config.node_id,
        )
        story_memory = StoryMemoryService(
            story_repo,
            entities=entities,
            federation=story_federation,
        )
        signal_repo = SignalRepository(db_path)
        event_store = EventStore(db_path)
        sourced_store = SourcedEventStore(db_path)
        publish_idempotency = PublishIdempotencyStore(db_path)
        workflow_store = WorkflowCheckpointStore(db_path)
        _caps = _runtime_caps()
        autonomous_runtime = build_autonomous_runtime(
            db_path,
            node_id=cluster_config.node_id,
            node_region=cluster_config.node_region,
            coordination=coordination,
            workflow_store=workflow_store,
            publish_idempotency=publish_idempotency,
        )
        cognitive_runtime = None
        cognitive_mesh = None
        epistemic_layer = None
        if _caps.research_stack:
            cognitive_runtime = build_cognitive_runtime(
                db_path,
                node_id=cluster_config.node_id,
                node_region=cluster_config.node_region,
            )
            if cluster_config.cluster_enabled:
                federated_learning = FederatedLearningSync(coordination)
            cognitive_mesh = build_federated_cognitive_mesh(
                db_path,
                cognitive_runtime,
                node_id=cluster_config.node_id,
                region=cluster_config.node_region,
                federated_sync=federated_learning,
            )
            epistemic_layer = build_epistemic_integrity_layer(
                db_path,
                cognitive_runtime,
                mesh=cognitive_mesh,
                node_id=cluster_config.node_id,
                region=cluster_config.node_region,
            )
        operations_platform = build_operations_platform(
            db_path,
            node_id=cluster_config.node_id,
            region=cluster_config.node_region,
        )
        from bot.operator_console.context import get_operator_console

        _op_console = get_operator_console()
        if _op_console is not None:
            _op_console.hub.attach_repository(operations_platform.repository)
        operations_platform.runtime_supervisor._queue_backlog_fn = registry.queue_backlog
        from bot.observability.loop_health import is_autonomous_passive_mode
        from bot.observability.loop_registry import reset_and_configure_loop_registry
        from bot.runtime.profile import log_startup_summary

        _caps = _runtime_caps()
        if is_autonomous_passive_mode() and _caps.autonomous_runtime == "passive":
            runtime_state.autonomous_passive = True
        reset_and_configure_loop_registry(_caps)
        log_startup_summary()
        logger.info("event=runtime_profile_selected profile=%s", _caps.profile.value)
        import os

        burnin_profile = os.getenv("OPS_BURNIN_PROFILE", settings.ops_burnin_profile)
        burnin_enabled = settings.is_staging or os.getenv("OPS_BURNIN_ENABLED", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if (
            _caps.burnin_auto_start
            and role_allows_operator(cluster_config.node_role)
            and burnin_enabled
        ):
            operations_platform.burnin.start(burnin_profile)
            logger.info("event=burnin_auto_started profile=%s", burnin_profile)
        if role_allows_operator(cluster_config.node_role):
            from bot.staging.context import install_publish_guard
            from bot.staging.shadow_publish import StagingPublishGuard

            install_publish_guard(
                StagingPublishGuard(
                    staging_mode=settings.is_staging,
                    shadow_only=runtime_state.shadow_publish_only,
                    blocked_channel_ids=settings.production_channel_blocklist_set,
                    repository=operations_platform.repository,
                )
            )
        from bot.reliability.context_holder import install_reliability
        from bot.reliability.factory import build_reliability_stack
        from bot.reliability.settings import ReliabilitySettings

        if ReliabilitySettings.from_env().enabled:

            async def _reliability_notify(
                text: str,
                *,
                severity: object,
                pinned: bool = False,
            ) -> None:
                from bot.operator_console.context import get_operator_console

                console = get_operator_console()
                if console is None:
                    return
                await console.send_raw(
                    text,
                    category="incident",
                    force=True,
                    silent=not pinned,
                )

            reliability_coordinator = build_reliability_stack(
                operations_platform,
                queue_depth_fn=registry.queue_backlog,
                operator_notify=_reliability_notify,
            )
            install_reliability(reliability_coordinator)
            logger.info("event=reliability_layer_installed")

        from bot.production_safety.context_holder import install_production_safety
        from bot.production_safety.factory import build_production_safety
        from bot.production_safety.settings import ProductionSafetySettings as PsSettings

        if PsSettings.from_env().enabled:

            def _dlq_depth() -> int:
                try:
                    from bot.distributed.stream.base import StreamEventBus

                    if isinstance(event_bus, StreamEventBus):
                        return event_bus.dead_letter_count
                except Exception:
                    pass
                return 0

            production_safety = build_production_safety(
                db_path,
                admin_ids=settings.admin_user_id_set,
                backup_chat_id=settings.telegram_operator_chat_id,
                dlq_depth_fn=_dlq_depth,
            )
            install_production_safety(production_safety)
            logger.info(
                "event=production_safety_installed stage=%s",
                production_safety.rollout.current_stage().value,
            )
        from bot.go_live.settings import GoLiveSettings

        if (
            _caps.go_live_stack
            and GoLiveSettings.from_env().enabled
            and publish_channel_id is not None
            and role_allows_operator(cluster_config.node_role)
        ):
            from bot.go_live.context_holder import install_go_live
            from bot.go_live.factory import build_go_live_stack

            go_live_coordinator = build_go_live_stack(db_path)
            _go_live_report = await go_live_coordinator.run_production_activation(
                bot,
                channel_id=publish_channel_id,
                operator_chat_id=settings.telegram_operator_chat_id,
                admin_user_ids=settings.admin_user_id_set,
                shadow_publish_only=runtime_state.shadow_publish_only,
                emergency_contacts=settings.go_live_emergency_contact_set,
                send_ping=settings.go_live_startup_ping,
                send_dashboard=settings.go_live_executive_dashboard,
            )
            if not _go_live_report.passed and settings.strict_startup_required:
                await _abort_staging_startup(
                    bot,
                    subsystem="go_live_telegram_activation",
                    settings=settings,
                    conn_report=conn_report,
                    alerts=alerts,
                    extra=_go_live_report.structured(),
                )
            install_go_live(go_live_coordinator)
            logger.info("event=go_live_installed passed=%s", _go_live_report.passed)
        from bot.operations.startup_validation import StartupValidationRunner

        startup_report = StartupValidationRunner.run(
            settings=settings,
            db_path=db_path,
            rss_feed_count=len(rss_feeds),
            telegram_report=conn_report,
            telemetry=telemetry,
            operations_platform=operations_platform,
            node_role=cluster_config.node_role,
        )
        if not startup_report.passed and settings.strict_startup_required:
            await _abort_staging_startup(
                bot,
                subsystem="startup_validation",
                settings=settings,
                conn_report=conn_report,
                startup_report=startup_report,
                alerts=alerts,
            )
        workflow_recovery = autonomous_runtime.recovery
        from bot.observability.tracing import init_tracing

        init_tracing(service_name=f"newsroom-{cluster_config.node_role}")
        event_bus = create_stream_bus(
            node_id=cluster_config.node_id,
            store=event_store,
            sourced_store=sourced_store,
            redis_url=cluster_config.redis_url,
        )
        event_bus.start()
        from bot.live_ops.context_holder import install_live_ops
        from bot.live_ops.factory import build_live_ops_stack
        from bot.live_ops.settings import LiveOpsSettings as LiveOpsSettingsCls

        if _caps.live_ops_stack and LiveOpsSettingsCls.from_env().enabled:
            live_ops_coordinator = build_live_ops_stack(
                db_path,
                stream_bus=event_bus,
                node_id=cluster_config.node_id,
            )
            install_live_ops(live_ops_coordinator)
            recovery_report = await live_ops_coordinator.startup()
            logger.info(
                "event=live_ops_installed mode=%s replayed=%d",
                recovery_report.mode,
                recovery_report.replayed_events,
            )
            if production_safety is not None:
                from bot.live_ops.bridge import wire_production_safety_hooks

                wire_production_safety_hooks(live_ops_coordinator, production_safety)
        from bot.ops_certification.context_holder import install_ops_certification
        from bot.ops_certification.factory import build_ops_certification
        from bot.ops_certification.settings import OpsCertificationSettings

        if _caps.ops_certification and OpsCertificationSettings.from_env().enabled:
            ops_certification_coordinator = build_ops_certification(
                db_path,
                node_id=cluster_config.node_id,
                region=cluster_config.node_region,
            )

            def _ops_cert_signals() -> dict:
                sig: dict = {"queue_depth": registry.queue_backlog(), "uptime_ok": True}
                if live_ops_coordinator is not None:
                    lo_snap = live_ops_coordinator.stability.rolling_score()
                    sig["stability_score"] = lo_snap
                    sig["event_bus_dlq"] = live_ops_coordinator.event_bus.dead_letter_count
                    sig["event_bus_pending"] = live_ops_coordinator.event_bus.pending_count
                    sig["worker_stale"] = len(live_ops_coordinator.workers.stale_workers())
                    sig["worker_total"] = len(live_ops_coordinator.workers.snapshot())
                    rec = live_ops_coordinator.recovery_report
                    sig["recovery_ok"] = rec.passed if rec else True
                    sig["replay_ok"] = rec.passed if rec else True
                if reliability_coordinator is not None:
                    sig["fatal_incidents"] = reliability_coordinator.incidents.recent_fatal_count()
                if production_safety is not None:
                    sig["budget_anomaly"] = False
                    sig["telegram_health"] = 0.95
                if ops_certification_coordinator is not None:
                    sig["poison_growth"] = ops_certification_coordinator.repository.poison_queue_count()
                stack = (
                    live_ops_coordinator.storage
                    if live_ops_coordinator is not None
                    else {}
                )
                sig["db_ok"] = bool(stack.get("primary_ok", True))
                return sig

            ops_certification_coordinator.configure_signals(_ops_cert_signals)
            await ops_certification_coordinator.startup()
            install_ops_certification(ops_certification_coordinator)
            logger.info("event=ops_certification_installed")
        from bot.rc1.context_holder import install_rc1
        from bot.rc1.factory import build_rc1_stack
        from bot.rc1.settings import Rc1Settings

        if _caps.rc1_stack and Rc1Settings.from_env().enabled:
            rc1_coordinator = build_rc1_stack(
                db_path,
                quiet_hour_start=settings.telegram_ops_quiet_hour_start,
                quiet_hour_end=settings.telegram_ops_quiet_hour_end,
            )

            def _rc1_signals() -> dict:
                base: dict = {}
                if ops_certification_coordinator is not None:
                    try:
                        base = _ops_cert_signals()
                    except NameError:
                        base = {"queue_depth": registry.queue_backlog()}
                else:
                    base = {"queue_depth": registry.queue_backlog()}
                base["certification"] = {}
                if ops_certification_coordinator and ops_certification_coordinator.last_certification:
                    base["certification"] = ops_certification_coordinator.last_certification.to_dict()
                if production_safety is not None:
                    base["rollout_stage"] = production_safety.rollout.current_stage().value
                val = (
                    rc1_coordinator.repository.latest_validation_scores()
                    if rc1_coordinator
                    else None
                )
                if val:
                    base["go_live_confidence"] = val.get("go_live_confidence")
                if reliability_coordinator is not None:
                    base["active_incidents"] = reliability_coordinator.incidents.recent_fatal_count()
                if live_ops_coordinator is not None:
                    base["stability_score"] = live_ops_coordinator.stability.rolling_score()
                    base["shadow_ratio"] = (
                        1.0 if runtime_state.shadow_publish_only else 0.0
                    )
                return base

            rc1_coordinator.configure_signals(_rc1_signals)
            config_report = await rc1_coordinator.startup()
            install_rc1(rc1_coordinator)
            if not config_report.passed and settings.is_staging and settings.staging_strict_startup:
                logger.error("event=rc1_config_validation_blocking_startup")
            else:
                logger.info(
                    "event=rc1_installed build=%s fingerprint=%s",
                    config_report.fingerprint,
                    config_report.passed,
                )
        from bot.ga_ops.context_holder import install_ga_ops
        from bot.ga_ops.factory import build_ga_ops_stack
        from bot.ga_ops.settings import GaOpsSettings

        if _caps.ga_ops and GaOpsSettings.from_env().enabled:
            ga_ops_coordinator = build_ga_ops_stack(db_path)

            def _ga_ops_signals() -> dict:
                sig: dict = {}
                try:
                    sig = _rc1_signals()
                except NameError:
                    sig = {"queue_depth": registry.queue_backlog()}
                if ops_certification_coordinator and ops_certification_coordinator.last_certification:
                    sig["certification_state"] = (
                        ops_certification_coordinator.last_certification.state.value
                    )
                if ops_certification_coordinator:
                    sig["slo_violations"] = sum(
                        1 for e in ops_certification_coordinator.slo.evaluate_all() if e.violated
                    )
                val = rc1_coordinator.repository.latest_validation_scores() if rc1_coordinator else None
                if val:
                    sig["go_live_confidence"] = val.get("go_live_confidence")
                    sig["publish_integrity"] = val.get("publish_integrity")
                sig["redis_enabled"] = bool(
                    live_ops_coordinator
                    and live_ops_coordinator.storage.get("redis"),
                )
                return sig

            ga_ops_coordinator.configure_signals(_ga_ops_signals)
            await ga_ops_coordinator.startup()
            install_ga_ops(ga_ops_coordinator)
            logger.info("event=ga_ops_installed")
        from bot.post_ga.context_holder import install_post_ga
        from bot.post_ga.factory import build_post_ga_stack
        from bot.post_ga.settings import PostGaSettings

        if _caps.post_ga and PostGaSettings.from_env().enabled:
            post_ga_coordinator = build_post_ga_stack(db_path)

            def _post_ga_signals() -> dict:
                sig: dict = {}
                try:
                    sig = _ga_ops_signals()
                except NameError:
                    sig = {"queue_depth": registry.queue_backlog()}
                if ga_ops_coordinator and ga_ops_coordinator._last_ga:
                    sig["go_live_confidence"] = ga_ops_coordinator._last_ga.score
                stab = post_ga_coordinator.repository.get_stability() if post_ga_coordinator else None
                if stab:
                    sig["autonomy_score"] = stab.get("autonomy_score")
                return sig

            post_ga_coordinator.configure_signals(_post_ga_signals)
            await post_ga_coordinator.startup()
            install_post_ga(post_ga_coordinator)
            logger.info("event=post_ga_installed")
        from bot.ops_evolution.context_holder import install_ops_evolution
        from bot.ops_evolution.factory import build_ops_evolution_stack
        from bot.ops_evolution.settings import OpsEvolutionSettings

        if _caps.ops_evolution and OpsEvolutionSettings.from_env().enabled:
            ops_evolution_coordinator = build_ops_evolution_stack(db_path)

            def _ops_evolution_signals() -> dict:
                sig: dict = {}
                try:
                    sig = _post_ga_signals()
                except NameError:
                    sig = {"queue_depth": registry.queue_backlog()}
                if post_ga_coordinator:
                    sig["quality_avg"] = post_ga_coordinator.quality.quality_confidence
                    sig["operator_attention"] = post_ga_coordinator.operator_load.attention_score
                    sig["trust_trend"] = post_ga_coordinator.governance.trust_trend()
                if ga_ops_coordinator and ga_ops_coordinator._last_ga:
                    sig["ga_score"] = ga_ops_coordinator._last_ga.score
                stab = (
                    post_ga_coordinator.repository.get_stability()
                    if post_ga_coordinator
                    else None
                )
                if stab:
                    sig["autonomy_score"] = stab.get("autonomy_score")
                    sig["fatigue_index"] = stab.get("fatigue_index")
                if ops_evolution_coordinator and ops_evolution_coordinator._last_safety:
                    sig["evolution_drift"] = ops_evolution_coordinator._last_safety.get(
                        "evolution_risk",
                        0,
                    )
                sig["failure_issues"] = sig.get("failure_issues", [])
                sig["uptime_score"] = 0.95
                sig["recovery_ok"] = 1.0
                sig["scaling_risk"] = sig.get("scaling_risk", 0.2)
                return sig

            ops_evolution_coordinator.configure_signals(_ops_evolution_signals)
            await ops_evolution_coordinator.startup()
            install_ops_evolution(ops_evolution_coordinator)
            logger.info("event=ops_evolution_installed")
        from bot.platform.context_holder import install_platform
        from bot.platform.factory import build_platform_stack
        from bot.platform.settings import PlatformSettings

        if _caps.platform_stack and PlatformSettings.from_env().enabled:
            platform_coordinator = build_platform_stack(db_path)

            def _platform_signals() -> dict:
                try:
                    sig = _ops_evolution_signals()
                except NameError:
                    sig = {"queue_depth": registry.queue_backlog()}
                if ops_evolution_coordinator:
                    sig["maturity_overall"] = (
                        ops_evolution_coordinator._last_maturity or {}
                    ).get("overall", 0)
                return sig

            platform_coordinator.configure_signals(_platform_signals)
            await platform_coordinator.startup()
            install_platform(platform_coordinator)
            logger.info("event=platform_installed")
        from bot.ops_playbook.settings import OpsPlaybookSettings

        if _caps.ops_playbook and OpsPlaybookSettings.from_env().enabled and role_allows_operator(
            cluster_config.node_role,
        ):
            from bot.ops_playbook.context_holder import install_ops_playbook
            from bot.ops_playbook.factory import build_ops_playbook_stack

            ops_playbook_coordinator = build_ops_playbook_stack(db_path)
            await ops_playbook_coordinator.startup()
            install_ops_playbook(ops_playbook_coordinator)
            logger.info("event=ops_playbook_installed")
        from bot.live_deploy.settings import LiveDeploySettings

        if _caps.live_deploy_stack and LiveDeploySettings.from_env().enabled and role_allows_operator(
            cluster_config.node_role,
        ):
            from bot.live_deploy.context_holder import install_live_deploy
            from bot.live_deploy.factory import build_live_deploy_stack

            live_deploy_coordinator = build_live_deploy_stack(db_path)
            await live_deploy_coordinator.startup()
            install_live_deploy(live_deploy_coordinator)
            logger.info("event=live_deploy_installed")
        from bot.week1.settings import Week1Settings

        if _caps.week1_stack and Week1Settings.from_env().enabled and role_allows_operator(
            cluster_config.node_role,
        ):
            from bot.week1.context_holder import install_week1
            from bot.week1.factory import build_week1_stack

            week1_coordinator = build_week1_stack(db_path)
            await week1_coordinator.startup()
            install_week1(week1_coordinator)
            logger.info("event=week1_stabilization_installed")
        from bot.operational_memory.settings import OperationalMemorySettings

        if _caps.operational_memory and OperationalMemorySettings.from_env().enabled and role_allows_operator(
            cluster_config.node_role,
        ):
            from bot.operational_memory.context_holder import install_opmem
            from bot.operational_memory.factory import build_opmem_stack

            opmem_coordinator = build_opmem_stack(db_path)
            await opmem_coordinator.startup()
            install_opmem(opmem_coordinator)
            logger.info("event=operational_memory_installed")
        from bot.live_ops.channel_settings import ControlledLiveSettings

        if _caps.controlled_live and ControlledLiveSettings.from_env().enabled and role_allows_operator(
            cluster_config.node_role,
        ):
            from bot.live_ops.context_holder import install_controlled_live
            from bot.live_ops.controlled_factory import build_controlled_live_stack

            controlled_live_coordinator = build_controlled_live_stack(db_path)
            pilot_startup = await controlled_live_coordinator.startup()
            install_controlled_live(controlled_live_coordinator)
            logger.info(
                "event=controlled_live_installed passed=%s",
                pilot_startup.get("passed"),
            )
            ops_ch = controlled_live_coordinator.settings.ops_channel_id
            if ops_ch and pilot_startup.get("passed"):
                from bot.live_ops.telegram_pilot import send_pilot_startup_banner

                await send_pilot_startup_banner(bot, ops_ch)
            from bot.runtime.profile import startup_summary_text

            try:
                await bot.send_message(
                    ops_ch,
                    startup_summary_text(_caps),
                    parse_mode="HTML",
                    disable_notification=True,
                )
            except Exception:
                logger.exception("event=runtime_profile_banner_failed")
        if go_live_coordinator is not None and _caps.go_live_stack:

            def _go_live_signals() -> dict:
                sig: dict = {}
                try:
                    sig = _ops_evolution_signals()
                except NameError:
                    try:
                        sig = _post_ga_signals()
                    except NameError:
                        sig = {"queue_depth": registry.queue_backlog()}
                if production_safety is not None:
                    sig["rollout_stage"] = production_safety.rollout.current_stage().value
                if ga_ops_coordinator and ga_ops_coordinator._last_ga:
                    sig["go_live_confidence"] = ga_ops_coordinator._last_ga.score
                    sig["ga_ready"] = ga_ops_coordinator._last_ga.score >= 0.88
                if ops_certification_coordinator is not None:
                    cert_st = ops_certification_coordinator.repository.get_certification_state()
                    sig["certified"] = bool(cert_st and cert_st.get("certified"))
                return sig

            go_live_coordinator.configure_signals(_go_live_signals)
        if ops_playbook_coordinator is not None:

            def _playbook_signals() -> dict:
                sig: dict = {}
                try:
                    sig = _go_live_signals()
                except NameError:
                    try:
                        sig = _platform_signals()
                    except NameError:
                        sig = {"queue_depth": registry.queue_backlog()}
                sig["queue_depth"] = registry.queue_backlog()
                sig["open_incidents"] = len(sig.get("failure_issues", []))
                sig["rollback_ready"] = True
                sig["risk_forecast"] = sig.get("ecosystem_risk", sig.get("scaling_risk", 0.3))
                sig["publish_pressure"] = min(1.0, sig.get("queue_depth", 0) / 200.0)
                sig["audience_health"] = sig.get("quality_avg", 0.85)
                if ops_evolution_coordinator:
                    sig["pending_optimizations"] = len(
                        ops_evolution_coordinator.repository.pending_strategies(),
                    )
                    sig["maturity_overall"] = (
                        ops_evolution_coordinator._last_maturity or {}
                    ).get("overall", 0)
                if editorial is not None:
                    try:
                        sig["pending_approvals"] = obs_repo.count_pending_queue()  # type: ignore[union-attr]
                    except Exception:
                        sig["pending_approvals"] = sig.get("queue_depth", 0)
                sig["is_production"] = settings.is_production
                sig["slo_compliance"] = 0.98 if sig.get("certified") else 0.9
                sig["war_room_active"] = bool(
                    ops_playbook_coordinator.repository.active_war_room(),
                )
                sig["campaign_active"] = bool(
                    ops_playbook_coordinator.campaign.active_config(),
                )
                sig["ga_healthy"] = float(sig.get("go_live_confidence", 0)) >= 0.75
                sig["ga_ready_score"] = float(sig.get("go_live_confidence", 0))
                sig["publish_health"] = float(sig.get("quality_avg", 0.85))
                sig["operator_readiness"] = 1.0 - float(sig.get("operator_attention", 0.5))
                sig["quality_confidence"] = float(sig.get("quality_avg", 0.85))
                sig["scaling_pressure"] = float(sig.get("scaling_risk", 0.2))
                sig["certification_state"] = (
                    "CERTIFIED" if sig.get("certified") else "PENDING"
                )
                sig["active_risks"] = sig.get("failure_issues", [])[:5]
                return sig

            ops_playbook_coordinator.configure_signals(_playbook_signals)
            if live_deploy_coordinator is not None:
                live_deploy_coordinator.configure_signals(_playbook_signals)
            if week1_coordinator is not None:
                week1_coordinator.configure_signals(_playbook_signals)
            if opmem_coordinator is not None:
                opmem_coordinator.configure_signals(_playbook_signals)
            if controlled_live_coordinator is not None:
                controlled_live_coordinator.configure_signals(_playbook_signals)
        elif live_deploy_coordinator is not None:

            def _live_deploy_signals_only() -> dict:
                return {"queue_depth": registry.queue_backlog()}

            live_deploy_coordinator.configure_signals(_live_deploy_signals_only)
            if opmem_coordinator is not None:
                opmem_coordinator.configure_signals(_live_deploy_signals_only)
            if controlled_live_coordinator is not None:
                controlled_live_coordinator.configure_signals(_live_deploy_signals_only)
        if _caps.research_stack:
            EditorialAgentRouter(event_bus)
        if _caps.cluster_coordinator and cluster_config.cluster_enabled:
            cluster_coordinator = ClusterCoordinator(
                coordination,
                cluster_config,
                event_bus=event_bus,
            )
            cluster_coordinator.start()
            cluster_scheduler = autonomous_runtime.scheduler
        signal_intel = SignalIntelligenceService(
            signal_repo,
            story_repo=story_repo,
            sources=sources,
            entities=entities,
            event_bus=event_bus,
        )
        control_plane = ControlPlane.build(
            db_path,
            sources=sources,
            obs=obs_repo,
            signal_repo=signal_repo,
        )
        adaptive = AdaptiveOperationsService(control_plane)
        runtime_state.operational_mode = control_plane.policies.current_mode()
        digest_service = DigestService(
            DigestRepository(db_path),
            publisher,
            entities,
            analytics,
            localizations,
            channel_router,
            story_repo=story_repo,
        )
        telegram_seen = TelegramSeenRepository(db_path)
        agents = EditorialAgentService(
            agent_repo,
            editorial,
            publisher,
            clusters=clusters,
            sources=sources,
            entities=entities,
            analytics=analytics,
            link_dedup=link_dedup,
            channel_router=channel_router,
            localizations=localizations,
        )
        runtime_state.auto_approval_enabled = settings.auto_approval_enabled
        runtime_state.enabled_languages = set(settings.enabled_languages)
        logger.info(
            "event=db_init_success",
            path=str(db_path),
            semantic_threshold=settings.semantic_similarity_threshold,
            languages=sorted(runtime_state.enabled_languages),
            node_id=cluster_config.node_id,
            node_role=cluster_config.node_role,
            event_bus=cluster_config.event_bus_backend,
        )
    except Exception:
        logger.exception("event=db_init_failed", path=str(default_db_path()))
        link_dedup = create_memory_link_dedup()
        telegram_seen = None
        await alerts.critical("Database initialization failed")

    if editorial is None:
        logger.error("event=editorial_queue_unavailable", reason="db_init_failed")
    else:
        _task_caps = _runtime_caps()
        registry.rss_ingestion_running = bool(rss_feeds) and _task_caps.rss_ingestion
        registry.digest_scheduler_running = _task_caps.digest_scheduler
        registry.analytics_scheduler_running = _task_caps.analytics_scheduler

        if _task_caps.rss_ingestion and role_allows_ingest(cluster_config.node_role):
            ingestion_task = asyncio.create_task(
                run_ingestion_loop(
                    rss_feeds,
                    link_dedup,
                    editorial,
                    clusters,
                    sources,
                    entities,
                    analytics,
                    agents,
                    localizations,
                    story_memory=story_memory,
                    signal_intel=signal_intel,
                    adaptive=adaptive,
                    registry=registry,
                    feed_resilience=(
                        operations_platform.feed_resilience
                        if operations_platform is not None
                        else None
                    ),
                ),
                name="rss-ingestion",
            )
        if _task_caps.digest_scheduler and role_allows_digest(cluster_config.node_role):
            digest_task = asyncio.create_task(
                run_digest_scheduler(
                    digest_service,
                    cluster_scheduler=cluster_scheduler,
                ),
                name="digest-scheduler",
            )
        telethon_settings = None
        if telethon_configured(settings):
            telethon_settings = TelethonSettings(
                api_id=int(settings.telegram_api_id),
                api_hash=str(settings.telegram_api_hash),
                session_name=settings.telegram_session_name,
                source_channels=settings.telegram_source_channel_list,
            )
        if _task_caps.telegram_ingestion and telethon_configured(settings):
            registry.telegram_ingestion_running = True
            telegram_task = asyncio.create_task(
                run_telegram_ingestion_loop(
                    telethon_settings,
                    settings.telegram_source_channel_list,
                    telegram_seen,
                    link_dedup,
                    editorial,
                    clusters,
                    sources,
                    entities,
                    analytics,
                    agents,
                    localizations,
                    story_memory=story_memory,
                    signal_intel=signal_intel,
                    adaptive=adaptive,
                    registry=registry,
                ),
                name="telegram-ingestion",
            )
        else:
            logger.warning("event=telegram_ingestion_disabled")

        if _task_caps.analytics_scheduler:
            analytics_task = asyncio.create_task(
                run_analytics_scheduler(
                    analytics,
                    bot,
                    channel_id=settings.telegram_channel_id,
                    telethon_settings=telethon_settings,
                ),
                name="analytics-scheduler",
            )

        if _task_caps.openai_daily_aggregate and obs_repo is not None:
            openai_agg_task = asyncio.create_task(
                run_openai_daily_aggregation_loop(obs_repo),
                name="openai-daily-aggregate",
            )

    if settings.health_http_port > 0:
        health_task = await serve_health_http(
            registry,
            host=settings.health_http_bind,
            port=settings.health_http_port,
            db_path=str(db_path) if operations_platform is not None else None,
            ops_platform=operations_platform,
            startup_report=startup_report,
        )

    if settings.watchdog_enabled:
        watchdog = BurnInWatchdog(
            registry,
            alerts,
            interval_sec=settings.watchdog_interval_sec,
            queue_backlog_threshold=settings.queue_backlog_alert_threshold,
        )
        from bot.runtime.instance import set_watchdog_active

        set_watchdog_active(True)
        watchdog_task = asyncio.create_task(watchdog.run(), name="burn-in-watchdog")

    import os as _os_forensics

    if _os_forensics.getenv("OPS_FORENSICS_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        from bot.ops_forensics.snapshots import runtime_snapshot_loop

        forensics_snapshot_task = asyncio.create_task(
            runtime_snapshot_loop(),
            name="forensics-runtime-snapshot",
        )

    import os as _os_lifecycle

    lifecycle_maint_task = None
    if _os_lifecycle.getenv("OPS_LIFECYCLE_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        from bot.ops_lifecycle.maintenance import lifecycle_maintenance_loop

        lifecycle_maint_task = asyncio.create_task(
            lifecycle_maintenance_loop(db_path),
            name="ops-lifecycle-maintenance",
        )

    import os as _os_resilience

    resilience_task = None
    if _os_resilience.getenv("OPS_RESILIENCE_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        from bot.ops_resilience.service import resilience_evaluation_loop

        resilience_task = asyncio.create_task(
            resilience_evaluation_loop(db_path),
            name="ops-resilience-evaluation",
        )

    async def _story_maintenance_loop() -> None:
        while True:
            try:
                if story_memory is not None:
                    story_memory.maintenance_pass()
                if signal_intel is not None:
                    signal_intel.maintenance_pass()
                if control_plane is not None:
                    result = control_plane.run_learning_cycle()
                    if federated_learning is not None and result.get("scores"):
                        scores = result["scores"]
                        federated_learning.sync_signal_precision(
                            {
                                "precision": scores.signal_precision_score,
                                "snr": scores.signal_to_noise_ratio,
                            },
                        )
                if workflow_recovery is not None:
                    await workflow_recovery.recover_orphans()
                    await workflow_recovery.recover_stalled()
            except Exception:
                logger.exception("event=story_maintenance_failed")
            await asyncio.sleep(3600)

    async def _stream_metrics_loop() -> None:
        while True:
            try:
                from bot.distributed.stream.base import StreamEventBus
                from bot.observability.metrics import set_stream_pending

                if isinstance(event_bus, StreamEventBus):
                    set_stream_pending(event_bus.pending_count)
            except Exception:
                logger.exception("event=stream_metrics_failed")
            await asyncio.sleep(15)

    if _runtime_caps().story_maintenance and (
        story_memory is not None or signal_intel is not None or control_plane is not None
    ):
        story_maint_task = asyncio.create_task(
            _story_maintenance_loop(),
            name="story-maintenance",
        )

    async def _metrics_refresh_loop() -> None:
        while True:
            try:
                backlog = registry.queue_backlog()
                set_queue_backlog(backlog)
                tasks = [
                    t
                    for t in (
                        ingestion_task,
                        digest_task,
                        telegram_task,
                        analytics_task,
                        watchdog_task,
                        health_task,
                        openai_agg_task,
                    )
                    if t is not None and not t.done()
                ]
                set_active_jobs(len(tasks))
            except Exception:
                logger.exception("event=metrics_refresh_failed")
            await asyncio.sleep(15)

    async def _autonomous_loop() -> None:
        import os
        import time as _time
        from bot.observability.loop_health import (
            LoopIterationStats,
            is_autonomous_passive_mode,
            record_autonomous_iteration,
        )
        from bot.observability.loop_registry import get_loop_registry

        passive_interval = max(90, int(os.getenv("AUTONOMOUS_PASSIVE_INTERVAL_SEC", "120")))
        active_interval = 45
        loop_reg = get_loop_registry()

        while True:
            tick_started = _time.perf_counter()
            sleep_sec = active_interval
            openai_dur = 0.0
            decision_dur = 0.0
            publish_dur = 0.0
            passive = is_autonomous_passive_mode()
            try:
                if autonomous_runtime is None:
                    await asyncio.sleep(60)
                    continue
                if passive:
                    sleep_sec = passive_interval
                    backlog = registry.queue_backlog()
                    result = await autonomous_runtime.tick(
                        node_id=cluster_config.node_id,
                        node_region=cluster_config.node_region,
                        is_leader=False,
                        queue_backlog=backlog,
                        apply_operations=False,
                        passive=True,
                    )
                else:
                    backlog = registry.queue_backlog()
                    dlq = 0
                    pending = 0
                    lag = 0.0
                    from bot.distributed.stream.base import StreamEventBus

                    if isinstance(event_bus, StreamEventBus):
                        dlq = event_bus.dead_letter_count
                        pending = event_bus.pending_count
                    dec_started = _time.perf_counter()
                    stalled = len(autonomous_runtime.recovery.analyze_stuck_graph())
                    decision_dur = _time.perf_counter() - dec_started
                    is_leader = (
                        cluster_coordinator.is_leader
                        if cluster_coordinator is not None
                        else False
                    )
                    result = await autonomous_runtime.tick(
                        node_id=cluster_config.node_id,
                        node_region=cluster_config.node_region,
                        is_leader=is_leader,
                        queue_backlog=backlog,
                        stream_lag_sec=lag,
                        dlq_count=dlq,
                        pending_stream=pending,
                        workflow_stalled=stalled,
                        apply_operations=False,
                        passive=False,
                    )
                    from bot.observability.metrics import set_scheduler_pressure

                    set_scheduler_pressure(float(result.get("pressure", 0)))
                logger.debug("event=autonomous_tick passive=%s %s", passive, result)
            except Exception:
                logger.exception("event=autonomous_tick_failed")
            finally:
                task_dur = _time.perf_counter() - tick_started
                record_autonomous_iteration(
                    LoopIterationStats(
                        loop_name="autonomous-runtime",
                        task_duration=task_dur,
                        openai_duration=openai_dur,
                        decision_duration=decision_dur,
                        publish_duration=publish_dur,
                        sleep_duration=float(sleep_sec),
                        passive=passive,
                    ),
                )
                loop_reg.heartbeat("autonomous-runtime", task_dur)
            await asyncio.sleep(sleep_sec)

    async def _cluster_metrics_loop() -> None:
        while True:
            try:
                if cluster_coordinator is not None:
                    nodes = cluster_coordinator.list_nodes(include_stale=True)
                    healthy = sum(1 for n in nodes if n.status == "healthy")
                    draining = sum(1 for n in nodes if n.status == "draining")
                    offline = sum(1 for n in nodes if n.status == "offline")
                    from bot.observability.metrics import set_cluster_nodes

                    set_cluster_nodes(healthy=healthy, draining=draining, offline=offline)
            except Exception:
                logger.exception("event=cluster_metrics_failed")
            await asyncio.sleep(30)

    metrics_task = asyncio.create_task(_metrics_refresh_loop(), name="metrics-refresh")
    if cluster_coordinator is not None:
        cluster_metrics_task = asyncio.create_task(
            _cluster_metrics_loop(),
            name="cluster-metrics",
        )
    stream_metrics_task = asyncio.create_task(
        _stream_metrics_loop(),
        name="stream-metrics",
    )
    async def _cognitive_loop() -> None:
        while True:
            try:
                if cognitive_runtime is None:
                    await asyncio.sleep(90)
                    continue
                from bot.cognitive.predictive import OperationalSignals

                backlog = registry.queue_backlog()
                dlq = 0
                pending = 0
                lag = 0.0
                from bot.distributed.stream.base import StreamEventBus

                if isinstance(event_bus, StreamEventBus):
                    dlq = event_bus.dead_letter_count
                    pending = event_bus.pending_count
                deg_mode = "normal"
                if autonomous_runtime is not None:
                    deg_mode = autonomous_runtime.degradation.current().mode
                signals = OperationalSignals(
                    queue_backlog=backlog,
                    stream_lag_sec=lag,
                    dlq_count=dlq,
                    replay_backlog=pending,
                )
                result = await cognitive_runtime.tick(
                    signals=signals,
                    degradation_mode=deg_mode,
                )
                logger.debug("event=cognitive_tick %s", result)
            except Exception:
                logger.exception("event=cognitive_tick_failed")
            await asyncio.sleep(90)

    async def _mesh_loop() -> None:
        while True:
            try:
                if cognitive_mesh is None:
                    await asyncio.sleep(120)
                    continue
                is_leader = (
                    cluster_coordinator.is_leader if cluster_coordinator is not None else True
                )
                backlog = registry.queue_backlog()
                pressure = min(1.0, backlog / 500.0)
                regional = {cluster_config.node_region: pressure}
                if coordination is not None:
                    for node in coordination.list_nodes(include_stale=False)[:12]:
                        regional.setdefault(node.region, pressure * 0.8)
                if federated_learning is not None:
                    for key in ("mesh_quorum_evaluation", "mesh_learning_aggregated"):
                        remote = federated_learning.fetch(key)
                        if remote:
                            await cognitive_mesh.bus.ingest_remote(remote)
                result = await cognitive_mesh.tick(
                    is_leader=is_leader,
                    mesh_pressure=pressure,
                    regional_pressures=regional,
                )
                try:
                    from bot.observability.metrics import set_mesh_gossip_budget

                    remaining = cognitive_mesh.repository.gossip_budget_remaining(
                        cluster_config.node_id,
                        cluster_config.node_region,
                    )
                    set_mesh_gossip_budget(remaining)
                except Exception:
                    pass
                logger.debug("event=mesh_tick %s", result)
            except Exception:
                logger.exception("event=mesh_tick_failed")
            await asyncio.sleep(120)

    autonomous_task = None
    cognitive_task = None
    async def _operations_loop() -> None:
        from bot.observability.loop_registry import get_loop_registry
        import time as _time

        tick_count = 0
        loop_reg = get_loop_registry()
        while True:
            tick_started = _time.perf_counter()
            try:
                from bot.observability.loop_diagnostics import timed_async_job

                if operations_platform is None:
                    await asyncio.sleep(180)
                    continue
                backlog = registry.queue_backlog()
                mesh_health = 1.0
                epistemic_stability = 1.0
                if cognitive_mesh is not None:
                    mesh_health = float(
                        cognitive_mesh.repository.get_resilience().get("mesh_health", 1.0)
                    )
                if epistemic_layer is not None:
                    snap = epistemic_layer.repository.latest_snapshot("integrity_full")
                    if snap:
                        epistemic_stability = float(snap.get("federation_stability", 1.0))
                token_spend = 0.0
                if openai_tracker is not None and obs_repo is not None:
                    from datetime import datetime, timezone

                    day = datetime.now(timezone.utc).date().isoformat()
                    row = obs_repo.get_daily(day)
                    if row:
                        token_spend = float(row.cost_usd)
                epistemic_detail: dict = {}
                if epistemic_layer is not None:
                    snap = epistemic_layer.repository.latest_snapshot("integrity_full")
                    if snap:
                        epistemic_detail = {
                            "confidence_mean": float(snap.get("confidence_mean", 0.7)),
                            "uncertainty_mean": float(snap.get("uncertainty_mean", 0.3)),
                            "open_contradictions": int(snap.get("open_contradictions", 0)),
                            "misinfo_pressure": float(snap.get("misinfo_pressure", 0.0)),
                            "diversity_score": float(snap.get("diversity_score", 0.5)),
                        }
                open_c = int(epistemic_detail.get("open_contradictions", 0))
                tg_failures = operations_platform.repository.telegram_delivery_failure_count(
                    hours=6,
                )
                signals = {
                    "health_score": min(1.0, 1.0 - backlog / 1000.0),
                    "queue_backlog": backlog,
                    "epistemic_stability": epistemic_stability,
                    "mesh_health": mesh_health,
                    "token_spend_usd": token_spend,
                    "alerts_last_hour": 0,
                    "replay_divergence": 0.05,
                    "open_contradictions": open_c,
                    "telegram_failure_rate_6h": min(1.0, tg_failures / 10.0),
                    "loop_health": loop_reg.snapshot(),
                }
                longevity_period = None
                if tick_count > 0 and tick_count % 480 == 0:
                    longevity_period = "24h"
                elif tick_count > 0 and tick_count % 1440 == 0:
                    longevity_period = "72h"
                elif tick_count > 0 and tick_count % 3360 == 0:
                    longevity_period = "7d"
                async with timed_async_job("operations-platform-tick"):
                    result = await operations_platform.operational_tick(
                        signals=signals,
                        run_feed_validation=(tick_count > 0 and tick_count % 48 == 0),
                        run_storage_maintenance=(tick_count > 0 and tick_count % 96 == 0),
                        run_burnin_report=(tick_count % 192 == 0 and tick_count > 0),
                        run_epistemic_snapshot=(tick_count > 0 and tick_count % 32 == 0),
                        run_replay_indexes=(tick_count > 0 and tick_count % 24 == 0),
                        run_daily_economics=(tick_count % 480 == 0 and tick_count > 0),
                        run_nightly_cert=(tick_count == 481),
                        run_evidence_bundle=(tick_count > 0 and tick_count % 120 == 0),
                        run_longevity_report=longevity_period,
                        run_operator_workflow_report=(tick_count > 0 and tick_count % 96 == 0),
                        epistemic_detail=epistemic_detail,
                    )
                if production_safety is not None:
                    ps_snap = await production_safety.tick(
                        queue_depth=backlog,
                        obs_repo=obs_repo,
                        dlq_depth=0,
                    )
                    result["production_safety"] = ps_snap.to_dict()
                if reliability_coordinator is not None:
                    rel_result = await reliability_coordinator.tick(
                        operations=operations_platform,
                        registry=registry,
                        ops_report=result,
                        signals=signals,
                    )
                    result["reliability"] = rel_result.health
                    result["publish_gate"] = rel_result.publish_gate
                if live_ops_coordinator is not None:
                    live_snap = await live_ops_coordinator.tick(
                        queue_depth=backlog,
                        token_spend_hour=token_spend,
                    )
                    result["live_ops"] = live_snap.to_dict()
                if ops_certification_coordinator is not None:
                    cert_tick = await ops_certification_coordinator.tick(
                        signals={
                            "queue_depth": backlog,
                            "publish_latency_sec": None,
                            "cognition_sec": None,
                            "delivery_ok": True,
                            "uptime_ok": True,
                            "memory_mb": 0.0,
                            "fatal_incidents": (
                                reliability_coordinator.incidents.recent_fatal_count()
                                if reliability_coordinator
                                else 0
                            ),
                            "stability_score": (
                                live_ops_coordinator.stability.rolling_score()
                                if live_ops_coordinator
                                else 1.0
                            ),
                            "worker_stale": (
                                len(live_ops_coordinator.workers.stale_workers())
                                if live_ops_coordinator
                                else 0
                            ),
                            "worker_total": (
                                len(live_ops_coordinator.workers.snapshot())
                                if live_ops_coordinator
                                else 0
                            ),
                            "event_bus_dlq": (
                                live_ops_coordinator.event_bus.dead_letter_count
                                if live_ops_coordinator
                                else 0
                            ),
                            "event_bus_pending": (
                                live_ops_coordinator.event_bus.pending_count
                                if live_ops_coordinator
                                else 0
                            ),
                            "recovery_ok": True,
                            "replay_ok": True,
                            "budget_anomaly": False,
                            "telegram_health": 0.95,
                            "db_ok": True,
                            "poison_growth": ops_certification_coordinator.repository.poison_queue_count(),
                        },
                    )
                    result["ops_certification"] = cert_tick
                if rc1_coordinator is not None:
                    result["rc1"] = await rc1_coordinator.tick(
                        signals={
                            "queue_depth": backlog,
                            "event_bus_dlq": (
                                live_ops_coordinator.event_bus.dead_letter_count
                                if live_ops_coordinator
                                else 0
                            ),
                            "event_bus_pending": (
                                live_ops_coordinator.event_bus.pending_count
                                if live_ops_coordinator
                                else 0
                            ),
                            "worker_stale": (
                                len(live_ops_coordinator.workers.stale_workers())
                                if live_ops_coordinator
                                else 0
                            ),
                            "cognition_sec": None,
                            "retry_rate": 0.0,
                            "budget_hour": token_spend,
                            "telegram_health": 0.95,
                            "trust_score": 0.85,
                            "replay_ok": True,
                            "shadow_ratio": (
                                1.0 if runtime_state.shadow_publish_only else 0.0
                            ),
                        },
                    )
                    if tick_count > 0 and tick_count % 120 == 0:
                        rc1_coordinator.save_profile_snapshot()
                if ga_ops_coordinator is not None:
                    result["ga_ops"] = await ga_ops_coordinator.tick(
                        signals={
                            "queue_depth": backlog,
                            "worker_stale": (
                                len(live_ops_coordinator.workers.stale_workers())
                                if live_ops_coordinator
                                else 0
                            ),
                            "worker_total": (
                                len(live_ops_coordinator.workers.snapshot())
                                if live_ops_coordinator
                                else 0
                            ),
                            "event_bus_pending": (
                                live_ops_coordinator.event_bus.pending_count
                                if live_ops_coordinator
                                else 0
                            ),
                            "uptime_ok": True,
                            "critical_incidents": (
                                reliability_coordinator.incidents.recent_fatal_count()
                                if reliability_coordinator
                                else 0
                            ),
                            "certification_state": (
                                ops_certification_coordinator.last_certification.state.value
                                if ops_certification_coordinator
                                and ops_certification_coordinator.last_certification
                                else "NOT_READY"
                            ),
                            "slo_violations": (
                                sum(
                                    1
                                    for e in ops_certification_coordinator.slo.evaluate_all()
                                    if e.violated
                                )
                                if ops_certification_coordinator
                                else 0
                            ),
                            "go_live_confidence": 0.0,
                            "publish_integrity": 1.0,
                            "redis_enabled": bool(
                                live_ops_coordinator
                                and live_ops_coordinator.storage.get("redis")
                            ),
                        },
                    )
                if post_ga_coordinator is not None:
                    result["post_ga"] = await post_ga_coordinator.tick(
                        signals={
                            "queue_depth": backlog,
                            "trust_score": 0.85,
                            "slo_burn": (
                                sum(
                                    1
                                    for e in ops_certification_coordinator.slo.evaluate_all()
                                    if e.violated
                                )
                                / max(len(list(ops_certification_coordinator.slo.evaluate_all())), 1)
                                if ops_certification_coordinator
                                else 0.0
                            ),
                            "budget_hour": token_spend,
                            "scaling_risk": (
                                result.get("ga_ops", {}).get("scaling", {}).get("scaling_risk_score", 0)
                            ),
                            "failure_issues": result.get("rc1", {}).get("failure_issues", []),
                        },
                    )
                if ops_evolution_coordinator is not None:
                    result["ops_evolution"] = await ops_evolution_coordinator.tick(
                        signals={
                            "queue_depth": backlog,
                            "quality_avg": (
                                post_ga_coordinator.quality.quality_confidence
                                if post_ga_coordinator
                                else 0.8
                            ),
                            "trust_score": 0.85,
                            "autonomy_score": (
                                post_ga_coordinator.repository.get_stability() or {}
                            ).get("autonomy_score", 0.8)
                            if post_ga_coordinator
                            else 0.8,
                            "operator_attention": (
                                post_ga_coordinator.operator_load.attention_score
                                if post_ga_coordinator
                                else 1.0
                            ),
                            "scaling_risk": result.get("ga_ops", {})
                            .get("scaling", {})
                            .get("scaling_risk_score", 0),
                            "failure_issues": result.get("rc1", {}).get("failure_issues", []),
                            "ga_score": (
                                ga_ops_coordinator._last_ga.score
                                if ga_ops_coordinator and ga_ops_coordinator._last_ga
                                else 0.8
                            ),
                        },
                    )
                    if result.get("daily_report_pending"):
                        from bot.operator_console.context import get_operator_console

                        console = get_operator_console()
                        if console is not None:

                            async def _notify_report(t: str) -> None:
                                await console.send_raw(t, category="digest", force=True)

                            await reliability_coordinator.maybe_send_daily_report(
                                notify=_notify_report,
                            )
                        result.pop("daily_report_pending", None)
                if platform_coordinator is not None:
                    result["platform"] = await platform_coordinator.tick(
                        signals={
                            "queue_depth": backlog,
                            "failure_issues": result.get("rc1", {}).get(
                                "failure_issues",
                                [],
                            ),
                        },
                    )
                pb_sig: dict = {
                    "queue_depth": backlog,
                    "failure_issues": result.get("rc1", {}).get("failure_issues", []),
                    "quality_avg": (
                        post_ga_coordinator.quality.quality_confidence
                        if post_ga_coordinator
                        else 0.8
                    ),
                    "trust_score": 0.85,
                    "trust_trend": (
                        post_ga_coordinator.governance.trust_trend()
                        if post_ga_coordinator
                        else "stable"
                    ),
                    "engagement_quality": 0.75,
                    "uptime_score": 0.95,
                    "recovery_ok": 0.9,
                }
                if result.get("platform"):
                    pb_sig["ecosystem_risk"] = result["platform"].get("ecosystem_risk", 0)
                if ops_playbook_coordinator is not None:
                    result["ops_playbook"] = await ops_playbook_coordinator.tick(
                        signals=pb_sig,
                    )
                if week1_coordinator is not None:
                    result["week1"] = await week1_coordinator.tick(signals=pb_sig)
                    pb_sig["stabilization_risk"] = result["week1"].get(
                        "stabilization_risk",
                        0,
                    )
                    pb_sig["survivability_score"] = result["week1"].get(
                        "survivability_score",
                    )
                    pb_sig["confidence_trend"] = result["week1"].get(
                        "confidence_trend",
                        pb_sig.get("confidence_trend"),
                    )
                    pb_sig["noise_index"] = result["week1"].get("noise_index")
                    pb_sig["rollback_probability"] = result["week1"].get(
                        "rollback_probability",
                    )
                if opmem_coordinator is not None:
                    result["operational_memory"] = await opmem_coordinator.tick(
                        signals=pb_sig,
                    )
                if controlled_live_coordinator is not None:
                    result["controlled_live"] = await controlled_live_coordinator.tick(
                        signals=pb_sig,
                    )
                if live_deploy_coordinator is not None:
                    ld_tick = await live_deploy_coordinator.tick(signals=pb_sig)
                    result["live_deploy"] = ld_tick
                    for report_key in ld_tick.get("reports_due", []):
                        try:
                            from bot.operator_console.context import get_operator_console

                            console = get_operator_console()

                            if console is not None:

                                async def _exec_notify(t: str, _rk: str = report_key) -> None:
                                    await console.send_raw(
                                        t,
                                        category="digest",
                                        force=True,
                                    )

                                await live_deploy_coordinator.maybe_send_report(
                                    report_key,
                                    notify=_exec_notify,
                                )
                        except Exception:
                            logger.exception(
                                "event=executive_report_failed key=%s",
                                report_key,
                            )
                if week1_coordinator is not None:
                    w1_sig: dict = {"queue_depth": backlog}
                    if ops_playbook_coordinator is not None:
                        w1_sig = pb_sig
                    elif live_deploy_coordinator is not None:
                        w1_sig = {
                            "queue_depth": backlog,
                            "quality_avg": (
                                post_ga_coordinator.quality.quality_confidence
                                if post_ga_coordinator
                                else 0.8
                            ),
                        }
                    result["week1"] = await week1_coordinator.tick(signals=w1_sig)
                    w1_sig["stabilization_risk"] = result["week1"].get(
                        "stabilization_risk",
                        0,
                    )
                if tick_count > 0 and tick_count % 20 == 0:
                    await _post_hourly_burnin_telegram(
                        operations_platform=operations_platform,
                        mesh_health=mesh_health,
                        epistemic_detail=epistemic_detail,
                        result=result,
                    )
                ep_alerts = result.get("epistemic_alerts") or epistemic_detail.get("epistemic_alerts")
                if ep_alerts:
                    await _post_epistemic_incidents_telegram(
                        list(ep_alerts),
                        open_contradictions=int(epistemic_detail.get("open_contradictions", 0)),
                        operations_platform=operations_platform,
                        mesh_health=mesh_health,
                    )
                tick_count += 1
                logger.debug("event=operations_tick %s", result)
            except Exception:
                logger.exception("event=operations_tick_failed")
                loop_reg.heartbeat(
                    "operations-platform",
                    _time.perf_counter() - tick_started,
                    error="tick_failed",
                )
            else:
                loop_reg.heartbeat("operations-platform", _time.perf_counter() - tick_started)
            await asyncio.sleep(180)

    async def _operator_signal_loop() -> None:
        flush_sec = max(60, min(300, settings.telegram_ops_agg_window_sec))
        digest_every = max(1, settings.telegram_ops_digest_interval_sec // flush_sec)
        digest_tick = 0
        while True:
            try:
                from bot.operator_console.context import get_operator_console
                from bot.operator_console.scoring import compute_ops_health

                console = get_operator_console()
                if console is not None:
                    await console.flush_pending_signals()
                    fatigue = console.hub.fatigue.snapshot()
                    if operations_platform is not None:
                        console.hub.usability.persist(
                            operations_platform.repository, fatigue,
                        )
                    digest_tick += 1
                    if digest_tick >= digest_every and operations_platform is not None:
                        digest_tick = 0
                        open_c = operations_platform.repository.open_contradiction_count()
                        mesh_h = 1.0
                        if cognitive_mesh is not None:
                            mesh_h = float(
                                cognitive_mesh.repository.get_resilience().get(
                                    "mesh_health", 1.0,
                                )
                            )
                        epistab = 1.0
                        if epistemic_layer is not None:
                            snap = epistemic_layer.repository.latest_snapshot("integrity_full")
                            if snap:
                                epistab = float(snap.get("federation_stability", 1.0))
                        health = compute_ops_health(
                            queue_backlog=registry.queue_backlog(),
                            mesh_health=mesh_h,
                            epistemic_stability=epistab,
                            open_contradictions=open_c,
                            fatigue_score=fatigue.score,
                        )
                        digest_signals = {
                            "replay_lag": "stable",
                            "mesh_health": mesh_h,
                            "open_contradictions": open_c,
                            "misinfo_alerts": operations_platform.repository.pending_misinfo_alert_count(),
                            "storage_growth_mb": 0.0,
                        }
                        await console.hub.send_ops_digest(digest_signals, health)
                        budget = {}
                        if cognitive_mesh is not None:
                            budget = cognitive_mesh.repository.get_budget(cognitive_mesh.region)
                            await console.hub.send_cognition_digest(
                                mesh_health=mesh_h,
                                reasoning_spend=float(budget.get("spent_reasoning", 0)),
                                reasoning_quota=float(budget.get("reasoning_quota", 100)),
                            )
                        await console.hub.send_epistemic_digest(
                            open_contradictions=open_c,
                            misinfo_pending=operations_platform.repository.pending_misinfo_alert_count(),
                            epistemic_stability=epistab,
                        )
            except Exception:
                logger.exception("event=operator_signal_loop_failed")
            await asyncio.sleep(flush_sec)

    async def _epistemic_loop() -> None:
        while True:
            try:
                if epistemic_layer is None:
                    await asyncio.sleep(150)
                    continue
                mesh_health = 1.0
                if cognitive_mesh is not None:
                    res = cognitive_mesh.repository.get_resilience()
                    mesh_health = float(res.get("mesh_health", 1.0))
                backlog = registry.queue_backlog()
                result = await epistemic_layer.tick(
                    mesh_health=mesh_health,
                    queue_backlog=backlog,
                )
                open_count = int(result.get("open_contradictions", 0))
                if open_count >= settings.telegram_live_contradiction_threshold:
                    from bot.operator_console.context import get_operator_console

                    console = get_operator_console()
                    if console is not None:
                        await console.notify_contradiction_alert(
                            open_count=open_count,
                            top_items=epistemic_layer.contradictions.open_contradictions(
                                limit=5
                            ),
                        )
                logger.debug("event=epistemic_tick %s", result)
            except Exception:
                logger.exception("event=epistemic_tick_failed")
            await asyncio.sleep(150)

    async def _publish_safety_loop() -> None:
        while True:
            try:
                if operations_platform is None or not publisher.channel_configured:
                    await asyncio.sleep(900)
                    continue
                from bot.staging.context import get_publish_guard
                from bot.staging.publish_safety_monitor import PublishSafetyMonitor

                guard = get_publish_guard()
                if guard is None:
                    await asyncio.sleep(900)
                    continue
                monitor = PublishSafetyMonitor(guard, operations_platform.repository)
                safety = await monitor.check_channel_permissions(
                    bot,
                    publisher.channel_id,
                )
                if safety.issues:
                    operations_platform.incidents.open_incident(
                        title="Publish safety check failed",
                        severity="warning",
                        detail="; ".join(safety.issues)[:400],
                        correlation_key="publish_safety",
                        suggested_action="Verify shadow mode and channel admin rights",
                    )
            except Exception:
                logger.exception("event=publish_safety_loop_failed")
            await asyncio.sleep(1800)

    mesh_task = None
    epistemic_task = None
    operations_task = None
    publish_safety_task = None
    reliability_task = None

    async def _reliability_probe_loop() -> None:
        import time as _time
        from bot.observability.loop_registry import get_loop_registry
        from bot.reliability.settings import ReliabilitySettings

        reg = get_loop_registry()
        interval = ReliabilitySettings.from_env().probe_interval_sec
        while True:
            started = _time.perf_counter()
            try:
                if reliability_coordinator is not None:
                    reliability_coordinator.health.ingest_from_registry(registry)
                    reliability_coordinator.health.probe()
            except Exception:
                logger.exception("event=reliability_probe_failed")
            reg.heartbeat("reliability-probe", _time.perf_counter() - started)
            await asyncio.sleep(interval)

    from bot.runtime.profile import loop_enabled as _loop_enabled
    from bot.runtime.startup_cleanup import cancel_disabled_runtime_tasks

    _launch_caps = _runtime_caps()
    await cancel_disabled_runtime_tasks(_launch_caps)
    operator_signal_task = None
    autonomous_task = None
    cognitive_task = None
    mesh_task = None
    epistemic_task = None
    operations_task = None

    if _loop_enabled(_launch_caps.operator_signal_hub):
        operator_signal_task = asyncio.create_task(
            _operator_signal_loop(),
            name="operator-signal-hub",
        )
    if autonomous_runtime is not None and _loop_enabled(_launch_caps.autonomous_runtime):
        autonomous_task = asyncio.create_task(_autonomous_loop(), name="autonomous-runtime")
    if cognitive_runtime is not None and _loop_enabled(_launch_caps.cognitive_runtime):
        cognitive_task = asyncio.create_task(_cognitive_loop(), name="cognitive-runtime")
    if cognitive_mesh is not None and _loop_enabled(_launch_caps.federated_cognitive_mesh):
        mesh_task = asyncio.create_task(_mesh_loop(), name="federated-cognitive-mesh")
    if epistemic_layer is not None and _loop_enabled(_launch_caps.epistemic_integrity):
        epistemic_task = asyncio.create_task(_epistemic_loop(), name="epistemic-integrity")
    if _launch_caps.profile.value == "minimal_pilot" and controlled_live_coordinator is not None:
        from bot.runtime.minimal_pilot_loop import run_minimal_pilot_ops_loop

        operations_task = asyncio.create_task(
            run_minimal_pilot_ops_loop(
                registry=registry,
                controlled_live=controlled_live_coordinator,
            ),
            name="pilot-ops",
        )
    elif operations_platform is not None and _loop_enabled(_launch_caps.operations_platform):
        operations_task = asyncio.create_task(
            _operations_loop(),
            name="operations-platform",
        )
    if operations_platform is not None and role_allows_operator(cluster_config.node_role):
        publish_safety_task = asyncio.create_task(
            _publish_safety_loop(),
            name="publish-safety-monitor",
        )
    if reliability_coordinator is not None and _launch_caps.reliability_layer:
        reliability_task = asyncio.create_task(
            _reliability_probe_loop(),
            name="reliability-probe",
        )

    configure_admin_access(settings.admin_user_id_set)

    dp = Dispatcher()
    if editorial is not None and role_allows_operator(cluster_config.node_role):
        register_handlers(
            dp,
            publisher=publisher,
            editorial=editorial,
            clusters=clusters,
            digest_service=digest_service,
            link_dedup=link_dedup,
            settings=settings,
            sources=sources,
            entities=entities,
            analytics=analytics,
            agents=agents,
            agent_repo=agent_repo,
            channel_router=channel_router,
            localizations=localizations,
            story_memory=story_memory,
            signal_intel=signal_intel,
            adaptive=adaptive,
            publish_idempotency=publish_idempotency,
            node_id=cluster_config.node_id,
        )
        from bot.handlers.cluster_commands import register_cluster_handlers

        register_cluster_handlers(
            coordinator=cluster_coordinator,
            coordination=coordination,
            cluster_scheduler=cluster_scheduler,
            node_id=cluster_config.node_id,
            autonomous_runtime=autonomous_runtime,
        )
        if cognitive_runtime is not None:
            from bot.handlers.cognitive_commands import register_cognitive_handlers

            register_cognitive_handlers(cognitive_runtime=cognitive_runtime)
        if cognitive_mesh is not None:
            from bot.handlers.mesh_commands import register_mesh_handlers

            register_mesh_handlers(cognitive_mesh=cognitive_mesh)
        if epistemic_layer is not None:
            from bot.handlers.epistemic_commands import register_epistemic_handlers

            register_epistemic_handlers(epistemic_layer=epistemic_layer)
        from bot.handlers.operations_commands import register_operations_handlers

        register_operations_handlers(operations_platform=operations_platform)
        from bot.reliability.handlers import register_reliability_handlers

        register_reliability_handlers(reliability=reliability_coordinator)
        from bot.production_safety.handlers import register_production_safety_handlers

        register_production_safety_handlers(
            safety=production_safety,
            editorial=editorial,
        )
        from bot.live_ops.command_center.handlers import register_live_ops_handlers

        register_live_ops_handlers(
            live_ops=live_ops_coordinator,
            reliability=reliability_coordinator,
            safety=production_safety,
            queue_depth_fn=registry.queue_backlog,
        )
        from bot.ops_certification.command_center.handlers import (
            register_ops_certification_handlers,
        )

        register_ops_certification_handlers(
            ops_cert=ops_certification_coordinator,
            reliability=reliability_coordinator,
            safety=production_safety,
            queue_depth_fn=registry.queue_backlog,
        )
        from bot.rc1.command_center.handlers import register_rc1_handlers

        register_rc1_handlers(
            rc1=rc1_coordinator,
            ops_cert=ops_certification_coordinator,
            safety=production_safety,
            queue_depth_fn=registry.queue_backlog,
        )
        from bot.ga_ops.command_center.handlers import register_ga_ops_handlers

        register_ga_ops_handlers(
            ga_ops=ga_ops_coordinator,
            queue_depth_fn=registry.queue_backlog,
        )
        from bot.post_ga.command_center.handlers import register_post_ga_handlers

        register_post_ga_handlers(post_ga=post_ga_coordinator)
        from bot.ops_evolution.command_center.handlers import register_ops_evolution_handlers

        register_ops_evolution_handlers(evolution=ops_evolution_coordinator)
        from bot.platform.command_center.handlers import register_platform_handlers

        register_platform_handlers(platform=platform_coordinator)
        from bot.go_live.command_center.handlers import register_go_live_handlers

        register_go_live_handlers(go_live=go_live_coordinator)
        from bot.ops_playbook.command_center.handlers import register_ops_playbook_handlers

        register_ops_playbook_handlers(playbook=ops_playbook_coordinator)
        from bot.live_deploy.command_center.handlers import register_live_deploy_handlers

        register_live_deploy_handlers(live_deploy=live_deploy_coordinator)
        from bot.week1.command_center.handlers import register_week1_handlers

        register_week1_handlers(week1=week1_coordinator)
        from bot.operational_memory.command_center.handlers import register_opmem_handlers

        register_opmem_handlers(opmem=opmem_coordinator)
        from bot.live_ops.command_center.channel_handlers import (
            register_controlled_live_handlers,
        )

        register_controlled_live_handlers(controlled=controlled_live_coordinator)
        if cluster_coordinator is not None and ops_certification_coordinator is not None:
            ops_certification_coordinator.mesh.sync_from_cluster(
                leader=cluster_coordinator.current_leader(),
                node_id=cluster_config.node_id,
                region=cluster_config.node_region,
            )
        from bot.operator_console.handlers import register_operator_console_handlers

        register_operator_console_handlers(
            editorial=editorial,
            clusters=clusters,
            publisher=publisher,
            channel_router=channel_router,
            epistemic_layer=epistemic_layer,
            cognitive_mesh=cognitive_mesh,
            operations_platform=operations_platform,
            coordination=coordination,
            cluster_coordinator=cluster_coordinator,
            autonomous_runtime=autonomous_runtime,
            agents=agents,
            node_id=cluster_config.node_id,
            link_dedup=link_dedup,
            sources=sources,
            entities=entities,
            analytics=analytics,
            localizations=localizations,
            adaptive=adaptive,
            publish_idempotency=publish_idempotency,
        )
    else:
        from bot.handlers import router as bootstrap_router

        dp.include_router(bootstrap_router)

    if settings.is_staging and editorial is not None and startup_report is not None and startup_report.passed:
        from bot.operator_console.context import get_operator_console
        from bot.operations.startup_diagnostics import log_startup_ok

        check_status = {c.check_id: c.passed for c in startup_report.checks}

        def _chk(cid: str, default: bool = True) -> str:
            return "ok" if check_status.get(cid, default) else "fail"

        burnin_ok = "skip"
        if operations_platform is not None:
            active = operations_platform.repository.active_burnin()
            burnin_ok = "ok" if active else "pending"
        console = get_operator_console()
        log_startup_ok(
            telegram="ok" if conn_report.passed else "fail",
            redis=_chk("deps.redis"),
            postgres=_chk("deps.postgres"),
            feeds="ok" if rss_feeds else "empty",
            operator_console="ok" if console is not None else "fail",
            burnin=burnin_ok,
        )
        if settings.telegram_operator_chat_id and console is not None:
            try:
                await console.send_raw(
                    "✅ <b>Newsroom staging online</b>\n"
                    f"Feeds: {len(rss_feeds)} · Shadow publish: on\n"
                    "Commands: /runtime_live /topology_live /mesh_live /ops_score\n"
                    "/incidents /explain_story /inspect_replay",
                    category="startup",
                    force=True,
                )
            except Exception:
                logger.exception("event=operator_startup_notify_failed")

    logger.info(
        "event=bot_starting mode=polling runtime_instance_id=%s",
        _runtime_identity.runtime_instance_id,
    )
    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        registry.scheduler_running = False
        for task in (
            ingestion_task,
            digest_task,
            telegram_task,
            analytics_task,
            watchdog_task,
            health_task,
            openai_agg_task,
            metrics_task,
            story_maint_task,
            cluster_metrics_task,
            stream_metrics_task,
            autonomous_task,
            cognitive_task,
            mesh_task,
            epistemic_task,
            operations_task,
            operator_signal_task,
            publish_safety_task,
            reliability_task,
            forensics_snapshot_task,
        ):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if event_bus is not None:
            await event_bus.stop()
        if cluster_coordinator is not None:
            await cluster_coordinator.stop()
        from bot.distributed.redis_client import close_redis

        if production_safety is not None:
            production_safety.telegram.pause_publish(reason="graceful_shutdown")
            logger.info("event=graceful_shutdown_draining publish_paused=true")
        await close_redis()
        await bot.session.close()
        release_runtime_ownership()
        logger.info(
            "event=bot_stopped runtime_instance_id=%s",
            _runtime_identity.runtime_instance_id,
        )


def main() -> None:
    print("Starting bot...")
    asyncio.run(run())


if __name__ == "__main__":
    main()
