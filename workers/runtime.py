"""Async worker runtime: leased dequeue, retries, concurrency, graceful drain."""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from dataclasses import replace

from worker.job_queue import JobEnvelope, JobKind
from worker.reliable_transport import get_reliable_transport

from utils.queue_diagnostics import collect_queue_pressure, queue_drift_warnings, queue_saturation_warnings

from workers import state as worker_state
from workers import watchdog as runtime_watchdog
from workers.base import WorkerRole, install_shutdown_signals, worker_log_extra
from workers.dispatcher import HandlerContext, HandlerRegistry
from workers.retry import (
    build_policy_from_settings,
    classify_exception,
    permanent_never_retries,
)
from workers.types import ErrorClass, StructuredJobError
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


class WorkerRuntime:
    """
    Cooperative worker loop:
    - short BRPOPLPUSH / wait timeouts (does not block shutdown indefinitely)
    - visibility leases + startup recovery sweep
    - per-job wall timeout + handler panic isolation (non-Exception surfaced as job failure)
    """

    def __init__(
        self,
        settings: object,
        *,
        role: WorkerRole,
        job_kind: JobKind,
        registry: HandlerRegistry,
        bot: object | None = None,
        openai: object | None = None,
    ) -> None:
        self.settings = settings
        self.role = role
        self.job_kind = job_kind
        self.registry = registry
        self.bot = bot
        self.openai = openai
        self._shutdown = asyncio.Event()
        self._sem = asyncio.Semaphore(int(settings.worker_max_concurrency))  # type: ignore[attr-defined]
        self._tasks: set[asyncio.Task[None]] = set()

    def request_shutdown(self) -> None:
        self._shutdown.set()

    def install_signals(self) -> None:
        install_shutdown_signals(
            self._shutdown,
            worker_role=self.role.value,
            instance_id=str(self.settings.worker_instance_id),  # type: ignore[attr-defined]
        )

    async def _heartbeat_loop(self) -> None:
        from worker.heartbeat import write_worker_heartbeat, write_worker_runtime_detail

        while not self._shutdown.is_set():
            try:
                await write_worker_heartbeat(self.settings, self.role.value)
                transport = get_reliable_transport()
                ctr = worker_state.runtime_counters_snapshot()
                diag = await worker_state.collect_runtime_diag(self.settings)
                merged_counters = {**ctr, **diag}
                pressure = await collect_queue_pressure(transport, self.job_kind, self.settings)
                for w in queue_saturation_warnings(self.settings, pressure):
                    log_event(
                        logger,
                        "worker.queue_pressure",
                        worker_role=self.role.value,
                        job_kind=self.job_kind.value,
                        **w,
                        **worker_log_extra(self.settings),
                    )
                for w in queue_drift_warnings(self.settings, pressure):
                    log_event(
                        logger,
                        "worker.queue_drift",
                        worker_role=self.role.value,
                        job_kind=self.job_kind.value,
                        **w,
                        **worker_log_extra(self.settings),
                    )
                for w in runtime_watchdog.evaluate_runtime_watchdogs(
                    self.settings,
                    worker_role=self.role.value,
                    job_kind=self.job_kind.value,
                    counters=merged_counters,
                    queue_pressure=pressure,
                ):
                    log_event(logger, "worker.runtime_watchdog", **w, **worker_log_extra(self.settings))
                snap = {
                    "pending": await transport.depth_pending(self.job_kind),
                    "processing": await transport.depth_processing(self.job_kind),
                    "counters": merged_counters,
                    "queue_pressure": pressure,
                }
                await write_worker_runtime_detail(self.settings, self.role.value, snap)
            except Exception as exc:
                log_event(
                    logger,
                    "worker.heartbeat_iteration_failed",
                    error=repr(exc),
                    **worker_log_extra(self.settings),
                )
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=5.0)
            except TimeoutError:
                continue

    async def run_forever(self) -> None:
        transport = get_reliable_transport()
        vis = int(self.settings.worker_visibility_sec)  # type: ignore[attr-defined]
        poll = float(self.settings.worker_poll_interval_sec)  # type: ignore[attr-defined]
        conc = int(self.settings.worker_max_concurrency)  # type: ignore[attr-defined]
        extra = worker_log_extra(self.settings)

        recovered = await transport.recover_stale(self.job_kind, visibility_sec=vis)
        log_event(
            logger,
            "worker.startup_recovery",
            worker_role=self.role.value,
            recovered_count=recovered,
            job_kind=self.job_kind.value,
            **extra,
        )

        log_event(
            logger,
            "worker.loop_started",
            worker_role=self.role.value,
            job_kind=self.job_kind.value,
            concurrency=conc,
            **extra,
        )

        hb_task = asyncio.create_task(self._heartbeat_loop(), name="worker-heartbeat")

        try:
            while not self._shutdown.is_set():
                await self._reap_done_tasks()
                while len(self._tasks) >= conc:
                    await self._reap_done_tasks(wait_for_one=True)

                lease = await transport.lease_dequeue(
                    self.job_kind,
                    shutdown=self._shutdown,
                    visibility_sec=vis,
                    poll_timeout_sec=poll,
                )
                if lease is None:
                    continue
                raw_exact, env = lease
                delivery_id = str(env.payload.get("delivery_id") or "")
                t = asyncio.create_task(
                    self._run_with_semaphore(transport, raw_exact, env, delivery_id),
                    name=f"job:{delivery_id[:12]}",
                )
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("worker.heartbeat_task_failed")

        grace = float(self.settings.worker_grace_shutdown_sec)  # type: ignore[attr-defined]
        log_event(logger, "worker.drain_wait", worker_role=self.role.value, grace_sec=grace, **extra)
        await asyncio.sleep(min(grace, 120.0))
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        log_event(logger, "worker.loop_stopped", worker_role=self.role.value, **extra)

    async def _reap_done_tasks(self, *, wait_for_one: bool = False) -> None:
        if not self._tasks:
            return
        if wait_for_one:
            await asyncio.wait(self._tasks, return_when=asyncio.FIRST_COMPLETED)
        else:
            done = {t for t in self._tasks if t.done()}
            if done:
                await asyncio.gather(*done, return_exceptions=True)

    async def _run_with_semaphore(
        self,
        transport: object,
        raw_exact: str,
        env: JobEnvelope,
        delivery_id: str,
    ) -> None:
        async with self._sem:
            await self._process_one(transport, raw_exact, env, delivery_id)

    async def _process_one(
        self,
        transport: object,
        raw_exact: str,
        env: JobEnvelope,
        delivery_id: str,
    ) -> None:
        extra = worker_log_extra(self.settings)
        job_type = str((env.payload or {}).get("job_type") or "")
        attempt = int(env.retry.attempt or 0)
        policy = build_policy_from_settings(self.settings, envelope_attempt=attempt)
        t0 = time.perf_counter()

        await worker_state.on_job_start(job_type or "unknown", delivery_id=delivery_id or None)

        ctx = HandlerContext(
            settings=self.settings,
            worker_role=self.role.value,
            worker_instance_id=str(self.settings.worker_instance_id),  # type: ignore[attr-defined]
            bot=self.bot,
            openai=self.openai,
        )

        try:
            try:
                async with asyncio.timeout(float(self.settings.worker_max_job_sec)):  # type: ignore[attr-defined]
                    await self.registry.dispatch(ctx, env)
            except asyncio.TimeoutError:
                log_event(
                    logger,
                    "worker.job_timeout",
                    delivery_id=delivery_id,
                    job_type=job_type,
                    **extra,
                )
                await self._handle_failure(
                    transport,
                    raw_exact,
                    env,
                    delivery_id,
                    asyncio.TimeoutError("job wall timeout"),
                    attempt,
                    policy,
                )
                return
            except asyncio.CancelledError:
                raise
            except KeyboardInterrupt:
                raise
            except BaseException as exc:
                log_event(
                    logger,
                    "worker.job_handler_error",
                    delivery_id=delivery_id,
                    job_type=job_type,
                    error=repr(exc),
                    **extra,
                )
                await self._handle_failure(transport, raw_exact, env, delivery_id, exc, attempt, policy)
                return

            await transport.ack(self.job_kind, raw_exact, delivery_id=delivery_id)
            await worker_state.on_job_finish(success=True, delivery_id=delivery_id or None)
            log_event(
                logger,
                "worker.job_ok",
                delivery_id=delivery_id,
                job_type=job_type,
                duration_sec=round(time.perf_counter() - t0, 4),
                **extra,
            )
        except BaseException as exc:
            await worker_state.on_panic()
            log_event(
                logger,
                "worker.job_panic_outer",
                delivery_id=delivery_id,
                error=repr(exc),
                **extra,
            )
            try:
                await transport.nack_requeue(self.job_kind, raw_exact, delivery_id=delivery_id)
            except Exception:
                logger.exception("worker.nack_after_panic_failed")
            await worker_state.on_job_finish(success=False, delivery_id=delivery_id or None)

    async def _handle_failure(
        self,
        transport: object,
        raw_exact: str,
        env: JobEnvelope,
        delivery_id: str,
        exc: BaseException,
        attempt: int,
        policy: object,
    ) -> None:
        extra = worker_log_extra(self.settings)
        cls = classify_exception(exc)
        job_type = str((env.payload or {}).get("job_type") or "")
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb_s = "".join(tb_lines)[-12000:]
        try:
            from utils.security_redaction import redact_traceback, redaction_enabled

            if redaction_enabled():
                tb_s = redact_traceback(tb_s)[-12000:]
        except Exception:
            pass
        dlq_base: dict[str, object] = {
            "failure_class": cls.value,
            "attempt": attempt,
            "job_type": job_type,
            "handler_traceback": tb_s,
        }
        if isinstance(exc, asyncio.TimeoutError):
            dlq_base["terminal_detail"] = "wall_timeout"

        if permanent_never_retries(cls) or (
            isinstance(exc, StructuredJobError) and exc.classification == ErrorClass.PERMANENT
        ):
            dlq_meta = {**dlq_base, "terminal": "permanent"}
            await transport.nack_dlq(
                self.job_kind,
                raw_exact,
                delivery_id=delivery_id,
                reason=repr(exc),
                dlq_meta=dlq_meta,
            )
            log_event(logger, "worker.job_terminal_dlq", delivery_id=delivery_id, classification=cls.value, **extra)
            await worker_state.on_job_finish(success=False, delivery_id=delivery_id or None)
            return

        if policy.exhausted(attempt) or policy.past_deadline():
            reason = f"retries_exhausted attempt={attempt} {repr(exc)}"
            dlq_meta = {
                **dlq_base,
                "terminal": "retries_exhausted",
                "retry_deadline_exceeded": bool(policy.past_deadline()),
                "policy_exhausted": bool(policy.exhausted(attempt)),
            }
            await transport.nack_dlq(
                self.job_kind,
                raw_exact,
                delivery_id=delivery_id,
                reason=reason,
                dlq_meta=dlq_meta,
            )
            log_event(logger, "worker.job_poison_dlq", delivery_id=delivery_id, attempt=attempt, **extra)
            await worker_state.on_job_finish(success=False, delivery_id=delivery_id or None)
            return

        delay = policy.next_delay_sec(attempt)
        await worker_state.on_retry()
        log_event(
            logger,
            "worker.job_retry",
            delivery_id=delivery_id,
            attempt=attempt + 1,
            delay_sec=round(delay, 4),
            classification=cls.value,
            **extra,
        )
        await asyncio.sleep(delay)
        new_retry = replace(env.retry, attempt=attempt + 1)
        new_env = replace(env, retry=new_retry)
        safe_retry = bool(getattr(self.settings, "worker_retry_safe", False))
        from utils.reliability_diagnostics import record_retry_trace

        record_retry_trace(
            delivery_id=delivery_id,
            attempt=attempt + 1,
            safe_order=safe_retry,
            phase="retry_scheduled",
        )
        if safe_retry:
            await transport.enqueue(new_env)
            try:
                await transport.ack(self.job_kind, raw_exact, delivery_id=delivery_id)
            except Exception:
                logger.exception("worker.ack_after_retry_enqueue_failed")
            record_retry_trace(
                delivery_id=delivery_id,
                attempt=attempt + 1,
                safe_order=True,
                phase="retry_enqueued_then_acked",
            )
        else:
            try:
                await transport.ack(self.job_kind, raw_exact, delivery_id=delivery_id)
            except Exception:
                logger.exception("worker.ack_before_retry_failed")
            await transport.enqueue(new_env)
            record_retry_trace(
                delivery_id=delivery_id,
                attempt=attempt + 1,
                safe_order=False,
                phase="retry_acked_then_enqueued",
            )
        await worker_state.on_job_finish(success=False, delivery_id=delivery_id or None)
