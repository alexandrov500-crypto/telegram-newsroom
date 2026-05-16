#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_settings():
    from app.config import load_settings

    return load_settings()


def cmd_runtime_summary(args: argparse.Namespace) -> int:
    from utils.observability import get_runtime_snapshot

    s = _load_settings()
    snap = get_runtime_snapshot(s)
    if args.json:
        print(json.dumps(snap, indent=2, default=str))
        return 0
    print("runtime summary (use --json for machine-readable)")
    print(f"  uptime_sec: {snap.get('uptime_sec')}")
    print(f"  asyncio_tasks: {snap.get('asyncio_tasks')}")
    print(f"  posts_collected_total: {snap.get('posts_collected_total')}")
    print(f"  drafts_generated_total: {snap.get('drafts_generated_total')}")
    print(f"  drafts_created_total: {snap.get('drafts_created_total')}")
    print(f"  drafts_published_total: {snap.get('drafts_published_total')}")
    print(f"  publish_failures_total: {snap.get('publish_failures_total')}")
    print(f"  scheduler: {snap.get('scheduler')}")
    return 0


def cmd_recent_events(args: argparse.Namespace) -> int:
    from utils.runtime_events import get_recent_runtime_events

    events = get_recent_runtime_events(args.limit)
    if args.json:
        print(json.dumps(events, indent=2, default=str))
        return 0
    for ev in events:
        print(f"{ev.get('seq')} {ev.get('kind')} {ev.get('message')}")
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    if args.json:
        print(json.dumps(snap, indent=2, default=str))
        return 0
    print("metrics (use --json)")
    for k, v in snap.get("counters", {}).items():
        print(f"  {k}: {v}")
    return 0


def cmd_diagnostics_dump(args: argparse.Namespace) -> int:
    from utils.runtime_dump import generate_runtime_dump

    s = _load_settings()
    dump = generate_runtime_dump(s, events_limit=args.limit)
    print(json.dumps(dump, indent=2 if args.json else None, default=str))
    return 0


def cmd_latest_snapshot(args: argparse.Namespace) -> int:
    from utils.runtime_state_store import load_latest_runtime_snapshot

    s = _load_settings()
    data = load_latest_runtime_snapshot(s)
    if not data:
        print("no snapshot files found" if not args.json else json.dumps(None))
        return 0
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    print(f"reason: {data.get('reason')}")
    print(f"recorded_at: {data.get('recorded_at_iso')}")
    print(f"recent_errors: {len(data.get('recent_errors') or [])}")
    return 0


def cmd_draft_queue(args: argparse.Namespace) -> int:
    import asyncio

    from db.models import Draft
    from db.repository import list_pending_drafts
    from db.session import close_db, init_db, session_scope

    settings = _load_settings()

    async def run() -> list[Draft]:
        await close_db()
        await init_db(settings.database_url)
        async with session_scope() as session:
            rows = await list_pending_drafts(session, limit=200)
        await close_db()
        return rows

    rows = asyncio.run(run())
    if args.json:
        pending = []
        for d in rows:
            head = (d.content or "").splitlines()[0].strip() if (d.content or "").splitlines() else ""
            if len(head) > 64:
                head = head[:61] + "…"
            pending.append({"id": int(d.id), "preview": head, "created_at": d.created_at.isoformat()})
        print(json.dumps({"pending": pending}, default=str))
        return 0
    if not rows:
        print("no pending drafts")
        return 0
    print("pending drafts (oldest first):")
    for d in rows:
        head = (d.content or "").splitlines()[0].strip() if (d.content or "").splitlines() else ""
        if len(head) > 64:
            head = head[:61] + "…"
        print(f"  {d.id}\t{head}")
    return 0


def cmd_healthcheck(args: argparse.Namespace) -> int:
    script = REPO / "docker" / "healthcheck.py"
    if not script.is_file():
        print("healthcheck script not found", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO))
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    if not args.json:
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
    else:
        print(json.dumps({"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}))
    return int(proc.returncode)


def cmd_runtime_health(args: argparse.Namespace) -> int:
    import asyncio

    from app.config import load_settings
    from db.session import close_db, init_db
    from utils.redis_client import close_redis, init_redis_from_settings
    from utils.runtime_health import gather_runtime_health
    from worker.job_queue import close_job_queue, init_job_queue

    s = load_settings()

    async def run() -> dict:
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        await init_redis_from_settings(s)
        await init_job_queue(s)
        try:
            return await gather_runtime_health(s, include_openai=False)
        finally:
            await close_job_queue()
            await close_redis()
            await close_db()

    snap = asyncio.run(run())
    if args.json:
        print(json.dumps(snap, indent=2, default=str))
    else:
        print("ok=", snap.get("ok"), "backend=", snap.get("database_backend"))
    return 0 if snap.get("ok") else 1


def _parse_job_kind(label: str):
    from worker.job_queue import JobKind

    u = (label or "").strip().lower()
    mapping = {"ingest": JobKind.INGEST, "ai": JobKind.AI, "publisher": JobKind.PUBLISHER}
    if u not in mapping:
        raise SystemExit(f"unknown job kind {label!r} (use ingest|ai|publisher)")
    return mapping[u]


def cmd_queue_pressure(args: argparse.Namespace) -> int:
    import asyncio

    from app.config import load_settings
    from utils.queue_diagnostics import collect_queue_pressure, queue_saturation_warnings
    from utils.redis_client import close_redis, init_redis_from_settings
    from worker.job_queue import close_job_queue, init_job_queue
    from worker.reliable_transport import close_reliable_transport, init_reliable_transport

    s = load_settings()
    kind = _parse_job_kind(args.kind)

    async def run() -> dict:
        await init_redis_from_settings(s)
        await init_job_queue(s)
        await init_reliable_transport(s)
        try:
            from worker.reliable_transport import get_reliable_transport

            transport = get_reliable_transport()
            pressure = await collect_queue_pressure(transport, kind, s)
            warns = queue_saturation_warnings(s, pressure)
            return {"pressure": pressure, "warnings": warns}
        finally:
            await close_reliable_transport()
            await close_job_queue()
            await close_redis()

    data = asyncio.run(run())
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    p = data.get("pressure") or {}
    print(f"kind={p.get('job_kind')} pending={p.get('pending_depth')} processing={p.get('processing_depth')}")
    print(f"oldest_pending_age_sec={p.get('oldest_pending_age_sec')} inflight_age_est={p.get('sample_inflight_age_sec')}")
    for w in data.get("warnings") or []:
        print(f"  warn: {w}")
    return 0


def cmd_worker_queue_snapshot(args: argparse.Namespace) -> int:
    import asyncio

    from app.config import load_settings
    from utils.queue_diagnostics import collect_queue_pressure
    from utils.redis_client import close_redis, init_redis_from_settings
    from worker.job_queue import JobKind, close_job_queue, init_job_queue
    from worker.reliable_transport import close_reliable_transport, get_reliable_transport, init_reliable_transport

    s = load_settings()

    async def run() -> dict:
        await init_redis_from_settings(s)
        await init_job_queue(s)
        await init_reliable_transport(s)
        try:
            transport = get_reliable_transport()
            out: dict = {}
            for k in JobKind:
                out[k.value] = {
                    "depths": {
                        "pending": await transport.depth_pending(k),
                        "processing": await transport.depth_processing(k),
                    },
                    "pressure": await collect_queue_pressure(transport, k, s),
                    "dlq_head": (await transport.list_dlq(k, limit=3))[:3],
                }
            return out
        finally:
            await close_reliable_transport()
            await close_job_queue()
            await close_redis()

    data = asyncio.run(run())
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    for name, block in data.items():
        d = (block or {}).get("depths") or {}
        print(f"{name}: pending={d.get('pending')} processing={d.get('processing')}")
    return 0


def cmd_dlq_list(args: argparse.Namespace) -> int:
    import asyncio

    from app.config import load_settings
    from utils.redis_client import close_redis, init_redis_from_settings
    from worker.job_queue import close_job_queue, init_job_queue
    from worker.reliable_transport import close_reliable_transport, get_reliable_transport, init_reliable_transport

    s = load_settings()
    kind = _parse_job_kind(args.kind)

    async def run() -> list:
        await init_redis_from_settings(s)
        await init_job_queue(s)
        await init_reliable_transport(s)
        try:
            transport = get_reliable_transport()
            return await transport.list_dlq(kind, limit=args.limit)
        finally:
            await close_reliable_transport()
            await close_job_queue()
            await close_redis()

    rows = asyncio.run(run())
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    for i, row in enumerate(rows):
        did = row.get("delivery_id", "")
        term = row.get("terminal", "")
        rsn = (row.get("reason") or "")[:120]
        print(f"  [{i}] delivery_id={did} terminal={term} reason={rsn}")
    return 0


def cmd_dlq_inspect(args: argparse.Namespace) -> int:
    import asyncio

    from app.config import load_settings
    from utils.redis_client import close_redis, init_redis_from_settings
    from worker.job_queue import close_job_queue, init_job_queue
    from worker.reliable_transport import close_reliable_transport, get_reliable_transport, init_reliable_transport

    s = load_settings()
    kind = _parse_job_kind(args.kind)

    async def run() -> dict | None:
        await init_redis_from_settings(s)
        await init_job_queue(s)
        await init_reliable_transport(s)
        try:
            transport = get_reliable_transport()
            rows = await transport.list_dlq(kind, limit=max(args.index + 1, 1))
            if args.index < 0 or args.index >= len(rows):
                return None
            row = dict(rows[args.index])
            orig = row.get("original")
            if isinstance(orig, str) and len(orig) > args.original_max_chars:
                row["original"] = orig[: args.original_max_chars] + "…(truncated)"
            return row
        finally:
            await close_reliable_transport()
            await close_job_queue()
            await close_redis()

    row = asyncio.run(run())
    if row is None:
        print("no such dlq index")
        return 1
    print(json.dumps(row, indent=2, default=str))
    return 0


def cmd_dlq_replay(args: argparse.Namespace) -> int:
    import asyncio

    from app.config import load_settings
    from utils.redis_client import close_redis, init_redis_from_settings
    from worker.job_queue import close_job_queue, init_job_queue
    from worker.reliable_transport import close_reliable_transport, get_reliable_transport, init_reliable_transport

    s = load_settings()
    kind = _parse_job_kind(args.kind)

    async def run() -> bool:
        await init_redis_from_settings(s)
        await init_job_queue(s)
        await init_reliable_transport(s)
        try:
            transport = get_reliable_transport()
            return await transport.replay_dlq_index(kind, index=args.index)
        finally:
            await close_reliable_transport()
            await close_job_queue()
            await close_redis()

    ok = asyncio.run(run())
    if not ok:
        print("replay failed (index out of range, parse error, or lrem miss)")
        return 1
    print("replayed_ok")
    return 0


def cmd_retry_stats(args: argparse.Namespace) -> int:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    keys = sorted(k for k in ctr if any(x in k.lower() for x in ("retry", "panic", "fail", "dlq", "job")))
    out = {k: ctr[k] for k in keys}
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    if not out:
        print("no matching counters in metrics export")
        return 0
    for k, v in out.items():
        print(f"  {k}: {v}")
    return 0


def cmd_editorial_stats(args: argparse.Namespace) -> int:
    from utils.editorial_analytics import export_editorial_analytics
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    ed = export_editorial_analytics(dict(snap.get("counters") or {}))
    if args.json:
        print(json.dumps(ed, indent=2, default=str))
        return 0
    print("editorial analytics (use --json)")
    for k, v in sorted(ed.items()):
        print(f"  {k}: {v}")
    return 0


def cmd_publishing_stats(args: argparse.Namespace) -> int:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    pub = int(ctr.get("publishes", 0))
    pf = int(ctr.get("publish_failures", 0))
    pr = int(ctr.get("scheduled_publish_fired", 0))
    out = {
        "publishes": pub,
        "publish_failures": pf,
        "scheduled_publish_fired": pr,
        "publish_success_rate": round(pub / max(1, pub + pf), 4),
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    for k, v in out.items():
        print(f"  {k}: {v}")
    return 0


def cmd_editorial_insights(args: argparse.Namespace) -> int:
    import asyncio

    from db.session import close_db, init_db, session_scope
    from utils.editorial_insights import collect_editorial_insights

    settings = _load_settings()

    async def run() -> dict:
        await close_db()
        await init_db(settings.database_url)
        async with session_scope() as session:
            out = await collect_editorial_insights(session)
        await close_db()
        return out

    data = asyncio.run(run())
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    print("editorial insights (use --json)")
    print(f"  pending_count: {data.get('pending_count')}")
    print(f"  moderation_bottleneck_hint: {data.get('moderation_bottleneck_hint')}")
    print(f"  publish_velocity_per_hour: {data.get('publish_velocity_per_hour')}")
    return 0


def cmd_trending_topics(args: argparse.Namespace) -> int:
    import asyncio

    from db.session import close_db, init_db, session_scope
    from utils.editorial_insights import collect_editorial_insights

    settings = _load_settings()

    async def run() -> list:
        await close_db()
        await init_db(settings.database_url)
        async with session_scope() as session:
            data = await collect_editorial_insights(session)
        await close_db()
        return list(data.get("trending_topics") or [])

    topics = asyncio.run(run())
    if args.json:
        print(json.dumps({"trending_topics": topics}, indent=2, default=str))
        return 0
    if not topics:
        print("no trending topics (insufficient draft samples)")
        return 0
    for row in topics:
        print(f"  {row.get('term')}: {row.get('count')}")
    return 0


def cmd_export_intelligence_report(args: argparse.Namespace) -> int:
    from pathlib import Path

    from utils.editorial_intelligence_report import build_editorial_intelligence_report
    from utils.runtime_reports import write_report

    s = _load_settings()
    payload = build_editorial_intelligence_report(s)
    out = Path(args.out)
    write_report(out, payload, fmt=args.format)
    print(str(out))
    return 0


def cmd_topic_stats(args: argparse.Namespace) -> int:
    from editorial.topic_memory import export_topic_snapshot

    s = _load_settings()
    rows = export_topic_snapshot(s.runtime_state_dir, limit=max(1, min(args.limit, 200)))
    if args.json:
        print(json.dumps({"topics": rows}, indent=2, default=str))
        return 0
    if not rows:
        print("no topic_memory rows (pipeline has not bumped topics yet)")
        return 0
    for r in rows:
        hint = (r.get("hint") or "")[:72]
        print(f"  count={r.get('count')}\tlast_ts={r.get('last_ts')}\t{hint}")
    return 0


def cmd_event_inspect(args: argparse.Namespace) -> int:
    from editorial.events import load_event_history

    s = _load_settings()
    rows = load_event_history(s.runtime_state_dir, limit=max(1, min(args.limit, 200)))
    if args.json:
        print(json.dumps({"events": rows}, indent=2, default=str))
        return 0
    if not rows:
        print("no event_history yet")
        return 0
    for i, r in enumerate(rows):
        fp = str(r.get("fingerprint") or "")[:16]
        ex = (str(r.get("combined_text_excerpt") or ""))[:100].replace("\n", " ")
        print(f"  [{i}] fp={fp}… excerpt={ex}…")
    return 0


def cmd_trend_report(args: argparse.Namespace) -> int:
    from editorial.trends import detect_topic_trends

    s = _load_settings()
    rep = detect_topic_trends(s.runtime_state_dir)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
        return 0
    bursts = rep.get("bursts") or []
    if not bursts:
        print("no burst-level trends (see topic-stats for raw memory)")
        return 0
    for b in bursts:
        print(
            f"  {b.get('hint')}: count={b.get('count')} momentum={b.get('trend_momentum')} "
            f"confidence={b.get('trend_confidence')} age_h={b.get('trend_age_hours')}"
        )
    return 0


def cmd_editorial_feedback_report(args: argparse.Namespace) -> int:
    import asyncio

    from db.session import close_db, init_db, session_scope
    from editorial.feedback import collect_editorial_feedback_stats

    settings = _load_settings()

    async def run() -> dict:
        await close_db()
        await init_db(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        try:
            async with session_scope() as session:
                return await collect_editorial_feedback_stats(session)
        finally:
            await close_db()

    data = asyncio.run(run())
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    counts = data.get("counts") or {}
    print("editorial feedback aggregates (7d recent sample)")
    print(f"  pending: {counts.get('pending')}  published: {counts.get('published')}  rejected: {counts.get('rejected')}")
    print(f"  acceptance_proxy: {data.get('acceptance_proxy')}  manual_edit_signals: {data.get('manual_edit_signals')}")
    print(f"  feedback_boost_heuristic: published-heavy moderation → small relevance boost (see docs)")
    return 0


def cmd_relevance_debug(args: argparse.Namespace) -> int:
    """Synthetic cluster → unified relevance (read-only; does not mutate topic memory)."""
    from datetime import datetime, timezone

    from db.models import RawPost
    from editorial.entities import extract_entities
    from editorial.event_models import EventEvolution
    from editorial.feedback import feedback_boost_from_stats
    from editorial.relevance import compute_unified_relevance
    from utils.source_reputation import export_channel_scores_for_priority

    s = _load_settings()
    now = datetime.now(timezone.utc)
    text = args.text
    posts: list[RawPost] = []
    for i, ch in enumerate(args.channels.split(",")):
        ch = ch.strip() or f"channel_{i}"
        posts.append(
            RawPost(
                id=9000 + i,
                channel_name=ch,
                message_id=i + 1,
                text=text,
                created_at=now,
                collected_at=now,
            )
        )
    evo = EventEvolution(
        kind=args.evolution,  # type: ignore[arg-type]
        continuity_score=float(args.continuity),
        related_fingerprint=None,
        reasons=("cli_relevance_debug",),
    )
    topic_row = {"hint": args.topic_hint, "count": int(args.topic_count), "last_ts": now.timestamp(), "fingerprints": []}
    ents = extract_entities(text)
    ch_sc = export_channel_scores_for_priority(s.runtime_state_dir)
    fb = feedback_boost_from_stats(None)
    dup_arg = float(args.duplicate_pct)
    dup = None if dup_arg < 0.0 else dup_arg
    rel = compute_unified_relevance(
        posts,
        channel_scores=ch_sc,
        evolution=evo,
        topic_row=topic_row,
        entity_hits=len(ents),
        duplicate_similarity_pct=dup,
        feedback_boost=fb,
    )
    out = {
        "explain": "Synthetic posts for operator debugging; scores match production heuristics.",
        "entity_hits": len(ents),
        "entities_preview": [{"kind": e.kind, "n": e.normalized} for e in ents[:12]],
        "relevance": rel.to_dict(),
    }
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print("relevance breakdown (total on 0–100 scale)")
    d = rel.to_dict()
    for k in ("freshness", "source_reputation", "topic_momentum", "entity_importance", "novelty", "duplicate_suppression", "editorial_preference_boost"):
        print(f"  {k}: {d.get(k)}")
    print(f"  weights: {d.get('weights')}")
    print(f"  TOTAL: {d.get('total')}")
    if d.get("notes"):
        print(f"  notes: {d.get('notes')}")
    if d.get("policy_notes"):
        print(f"  policy_notes: {d.get('policy_notes')}")
    return 0


def cmd_policy_debug(args: argparse.Namespace) -> int:
    from editorial.policy import load_editorial_policy_bundle, resolve_effective_policy

    s = _load_settings()
    b = load_editorial_policy_bundle(s)
    ch = (args.channel or "").strip().lower() or (str(s.source_channels[0]).lower() if s.source_channels else "")
    pol, trace = resolve_effective_policy(b, ch)
    out = {"effective_policy": pol.to_dict(), "policy_trace": list(trace), "bundle_channels": sorted(b.channel_policies.keys())}
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(f"channel={ch or '(default)'}")
    for k, v in sorted(pol.to_dict().items()):
        print(f"  {k}: {v}")
    return 0


def cmd_cadence_report(args: argparse.Namespace) -> int:
    from editorial.intelligence_store import cadence_state_path, load_json
    from editorial.suppression_memory import duplicate_burst_count

    s = _load_settings()
    data = load_json(cadence_state_path(s.runtime_state_dir), {})
    out = {"cadence": data, "duplicate_burst": duplicate_burst_count(s.runtime_state_dir)}
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(f"last_publish_unix={data.get('last_publish_unix')} recent_n={len(data.get('recent') or [])}")
    print(f"duplicate_burst={out['duplicate_burst']}")
    return 0


def cmd_suppression_report(args: argparse.Namespace) -> int:
    from editorial.intelligence_store import load_json, suppression_state_path
    from editorial.suppression_memory import duplicate_burst_count

    s = _load_settings()
    data = load_json(suppression_state_path(s.runtime_state_dir), {})
    out = {"suppression_state": data, "duplicate_burst": duplicate_burst_count(s.runtime_state_dir)}
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    ent = data.get("entries") or {}
    print(f"suppression_entries={len(ent)} duplicate_burst={out['duplicate_burst']}")
    return 0


def cmd_topic_saturation_report(args: argparse.Namespace) -> int:
    from editorial.topic_memory import export_topic_snapshot, topic_saturation

    s = _load_settings()
    rows = export_topic_snapshot(s.runtime_state_dir, limit=max(1, min(args.limit, 200)))
    enriched = []
    for r in rows:
        sat, reason = topic_saturation(r, burst_threshold=args.burst_threshold)
        enriched.append({**r, "saturated": sat, "saturation_reason": reason})
    if args.json:
        print(json.dumps({"topics": enriched}, indent=2, default=str))
        return 0
    for r in enriched:
        print(f"  count={r.get('count')} sat={r.get('saturated')} hint={(r.get('hint') or '')[:56]}")
    return 0


def cmd_editorial_drift_report(args: argparse.Namespace) -> int:
    import asyncio

    from db.session import close_db, init_db, session_scope
    from editorial.drift_detection import evaluate_editorial_drift
    from editorial.feedback import collect_editorial_feedback_stats

    s = _load_settings()

    async def run() -> tuple[dict | None, dict]:
        fb: dict | None = None
        await close_db()
        await init_db(
            s.database_url,
            pool_size=s.database_pool_size,
            max_overflow=s.database_max_overflow,
        )
        try:
            async with session_scope() as session:
                fb = await collect_editorial_feedback_stats(session)
        finally:
            await close_db()
        fbd = fb or {}
        metrics = {
            "suppression_rate": 0.0,
            "avg_confidence": 0.0,
            "avg_headline_quality": 0.0,
            "manual_edit_rate": float(fbd.get("manual_edit_signals") or 0) / max(1, int(fbd.get("recent_drafts_sampled") or 1)),
        }
        return fb, metrics

    fb, metrics = asyncio.run(run())
    drift = evaluate_editorial_drift(
        s.runtime_state_dir,
        current_metrics=metrics,
        current_feedback=fb,
        append_snapshot=not args.no_append,
    )
    if args.json:
        print(json.dumps(drift, indent=2, default=str))
        return 0
    print("warnings:", drift.get("warnings"))
    print("snapshot:", drift.get("snapshot"))
    return 0


def cmd_pipeline_decision_inspect(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from db.models import RawPost
    from editorial.entities import extract_entities
    from editorial.event_models import EventEvolution
    from editorial.pipeline_decision import evaluate_unified_cluster_stage
    from editorial.policy import dominant_channel_key, load_editorial_policy_bundle

    s = _load_settings()
    now = datetime.now(timezone.utc)
    text = args.text
    posts: list[RawPost] = []
    for i, ch in enumerate(args.channels.split(",")):
        ch = ch.strip() or f"ch_{i}"
        posts.append(
            RawPost(
                id=8000 + i,
                channel_name=ch,
                message_id=i + 1,
                text=text,
                created_at=now,
                collected_at=now,
            )
        )
    evo = EventEvolution(
        kind=args.evolution,  # type: ignore[arg-type]
        continuity_score=float(args.continuity),
        related_fingerprint=None,
        reasons=("cli_pipeline_inspect",),
    )
    ents = extract_entities(text)
    norms = tuple(e.normalized for e in ents)
    bundle = load_editorial_policy_bundle(s)
    dom = dominant_channel_key(posts)
    uni = evaluate_unified_cluster_stage(
        posts,
        settings=s,
        evolution=evo,
        topic_hint=args.topic_hint,
        fingerprint=args.fingerprint,
        combined_text=text,
        channel_scores={},
        feedback_stats=None,
        duplicate_similarity_pct=None,
        entity_hits=len(ents),
        entity_norms=norms,
        policy_bundle=bundle,
        dominant_channel_key=dom,
    )
    if args.json:
        print(json.dumps(uni.to_dict(), indent=2, default=str))
        return 0
    print("outcome", uni.outcome.value)
    print("suppress", uni.suppress_generation, "defer", uni.defer_to_next_tick)
    print("reasons", list(uni.reasons))
    return 0


def cmd_export_runtime_report(args: argparse.Namespace) -> int:
    from pathlib import Path

    from utils.editorial_intelligence_report import build_editorial_intelligence_report
    from utils.runtime_reports import (
        build_ai_governance_report,
        build_anomaly_report,
        build_moderation_report,
        build_publishing_report,
        build_runtime_summary_report,
        write_report,
    )

    s = _load_settings()
    payload = {
        "bundle": "runtime_operator",
        "runtime_summary": build_runtime_summary_report(s),
        "ai_governance": build_ai_governance_report(s),
        "moderation": build_moderation_report(s),
        "publishing": build_publishing_report(s),
        "anomalies": build_anomaly_report(s),
        "editorial_intelligence": build_editorial_intelligence_report(s),
    }
    out = Path(args.out)
    write_report(out, payload, fmt=args.format)
    print(str(out))
    return 0


def cmd_ai_analytics(args: argparse.Namespace) -> int:
    from utils.runtime_reports import build_ai_governance_report

    s = _load_settings()
    rep = build_ai_governance_report(s)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
        return 0
    ctr = rep.get("counters") or {}
    print("ai governance counters (use --json)")
    for k, v in sorted(ctr.items()):
        print(f"  {k}: {v}")
    return 0


def cmd_export_editorial_report(args: argparse.Namespace) -> int:
    from pathlib import Path

    from utils.runtime_reports import build_editorial_activity_report, write_report

    s = _load_settings()
    payload = build_editorial_activity_report(s)
    out = Path(args.out)
    write_report(out, payload, fmt=args.format)
    print(str(out))
    return 0


def cmd_export_ops_dashboard(args: argparse.Namespace) -> int:
    import asyncio
    import json
    from pathlib import Path

    from db.session import close_db, init_db
    from dashboard import build_operational_dashboard_bundle

    s = _load_settings()

    async def run() -> dict:
        await close_db()
        await init_db(
            s.database_url,
            pool_size=s.database_pool_size,
            max_overflow=s.database_max_overflow,
        )
        try:
            b = await build_operational_dashboard_bundle(s, include_openai=False)
            return b.to_dict()
        finally:
            await close_db()

    data = asyncio.run(run())
    out = Path(args.out)
    if args.format == "html":
        from utils.operational_reports import render_operational_html_bundle

        out.write_text(render_operational_html_bundle(data), encoding="utf-8")
    else:
        out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(str(out))
    return 0


def cmd_config_doctor(args: argparse.Namespace) -> int:
    import json

    from app.config_diagnostics import (
        build_config_doctor_report,
        missing_env_for_bootstrap,
        startup_config_summary_lines,
    )

    miss = missing_env_for_bootstrap()
    if args.preview_missing:
        if args.json:
            print(json.dumps({"missing_env": miss}, indent=2))
        else:
            print("missing_env:", ", ".join(miss) if miss else "(none)")
        return 1 if miss else 0

    s = _load_settings()
    rep = build_config_doctor_report(s)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
        return 0
    for line in startup_config_summary_lines(s):
        print(line)
    return 0


def cmd_runtime_integrity_check(args: argparse.Namespace) -> int:
    import json

    from utils.runtime_integrity import (
        summarize_runtime_state_dir,
        validate_event_history,
        validate_operational_timeline,
        validate_suppression_state,
    )

    s = _load_settings()
    tl = validate_operational_timeline(s.runtime_state_dir)
    sup = validate_suppression_state(s.runtime_state_dir)
    evh = validate_event_history(s.runtime_state_dir)
    summ = summarize_runtime_state_dir(s.runtime_state_dir)
    payload = {"timeline_issues": tl, "suppression_issues": sup, "event_history_issues": evh, "summary": summ}
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print("timeline_issues:", tl or "ok")
    print("suppression_issues:", sup or "ok")
    print("event_history_issues:", evh or "ok")
    print("summary:", summ)
    return 1 if (tl or sup or evh) else 0


def cmd_runtime_reset_suppression(args: argparse.Namespace) -> int:
    import json

    from editorial.suppression_memory import reset_suppression_state_emergency

    s = _load_settings()
    out = reset_suppression_state_emergency(s.runtime_state_dir)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(out)
    return 0


def cmd_runtime_compact_state(args: argparse.Namespace) -> int:
    import json

    from dashboard.timeline import compact_operational_timeline
    from editorial.drift_detection import compact_drift_snapshots
    from editorial.events import compact_event_history
    from editorial.suppression_memory import prune_expired_suppression_entries

    s = _load_settings()
    tl_age = None if float(args.timeline_max_age_sec) < 0 else float(args.timeline_max_age_sec)
    drift_age = None if float(args.drift_max_age_sec) < 0 else float(args.drift_max_age_sec)
    ev_age = None if float(args.event_history_max_age_sec) < 0 else float(args.event_history_max_age_sec)
    sup = prune_expired_suppression_entries(s.runtime_state_dir)
    tl = compact_operational_timeline(
        s.runtime_state_dir,
        max_entries=int(args.timeline_max_entries),
        max_age_sec=tl_age,
    )
    drift = compact_drift_snapshots(
        s.runtime_state_dir,
        max_entries=int(args.drift_max_entries),
        max_age_sec=drift_age,
    )
    evh = compact_event_history(
        s.runtime_state_dir,
        max_entries=int(args.event_history_max_entries),
        max_age_sec=ev_age,
    )
    payload = {"suppression_prune": sup, "timeline": tl, "drift_snapshots": drift, "event_history": evh}
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Newsroom read-only admin / debug CLI")
    parser.add_argument("--json", action="store_true", help="JSON output where applicable")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("runtime-summary", help="Print runtime snapshot summary")
    p_sum.set_defaults(func=cmd_runtime_summary)

    p_ev = sub.add_parser("recent-events", help="Print buffered runtime events")
    p_ev.add_argument("--limit", type=int, default=48)
    p_ev.set_defaults(func=cmd_recent_events)

    p_met = sub.add_parser("metrics", help="Print metrics export")
    p_met.set_defaults(func=cmd_metrics)

    p_dump = sub.add_parser("diagnostics-dump", help="Print full diagnostics dump JSON")
    p_dump.add_argument("--limit", type=int, default=64)
    p_dump.set_defaults(func=cmd_diagnostics_dump)

    p_snap = sub.add_parser("latest-snapshot", help="Load latest persisted operational snapshot")
    p_snap.set_defaults(func=cmd_latest_snapshot)

    p_q = sub.add_parser("draft-queue", help="List drafts awaiting moderation (PENDING)")
    p_q.set_defaults(func=cmd_draft_queue)

    p_es = sub.add_parser("editorial-stats", help="Lightweight editorial analytics (in-process)")
    p_es.set_defaults(func=cmd_editorial_stats)

    p_ps = sub.add_parser("publishing-stats", help="Publish counters and success rate")
    p_ps.set_defaults(func=cmd_publishing_stats)

    p_ei = sub.add_parser("editorial-insights", help="DB-backed editorial insights snapshot")
    p_ei.set_defaults(func=cmd_editorial_insights)

    p_tt = sub.add_parser("trending-topics", help="Trending topic terms from recent drafts")
    p_tt.set_defaults(func=cmd_trending_topics)

    p_er = sub.add_parser("export-runtime-report", help="Write bundled runtime/moderation/publish JSON or HTML report")
    p_er.add_argument("--out", required=True, help="Output file path")
    p_er.add_argument("--format", choices=("json", "html"), default="json")
    p_er.set_defaults(func=cmd_export_runtime_report)

    p_ed = sub.add_parser("export-editorial-report", help="Write editorial activity report (JSON or HTML)")
    p_ed.add_argument("--out", required=True)
    p_ed.add_argument("--format", choices=("json", "html"), default="json")
    p_ed.set_defaults(func=cmd_export_editorial_report)

    p_ops = sub.add_parser(
        "export-ops-dashboard",
        help="Write merged operational dashboard (runtime + editorial + warnings + timeline + analytics)",
    )
    p_ops.add_argument("--out", required=True)
    p_ops.add_argument("--format", choices=("json", "html"), default="json")
    p_ops.set_defaults(func=cmd_export_ops_dashboard)

    p_doc = sub.add_parser(
        "config-doctor",
        help="Print missing required env (--preview-missing) or loaded non-secret config summary",
    )
    p_doc.add_argument(
        "--preview-missing",
        action="store_true",
        help="Only check os.environ for vars required before load_settings(); exits 1 if any missing",
    )
    p_doc.set_defaults(func=cmd_config_doctor)

    p_int = sub.add_parser(
        "runtime-integrity-check",
        help="Validate operational_timeline.json + suppression_state.json under RUNTIME_STATE_DIR",
    )
    p_int.set_defaults(func=cmd_runtime_integrity_check)

    p_rs = sub.add_parser(
        "runtime-reset-suppression",
        help="Emergency: clear suppression_state.json entries + duplicate burst (does not touch topic/cadence)",
    )
    p_rs.set_defaults(func=cmd_runtime_reset_suppression)

    p_rc = sub.add_parser(
        "runtime-compact-state",
        help="Prune suppression TTL + trim timeline, drift snapshots, and event_history JSON files",
    )
    p_rc.add_argument("--timeline-max-entries", type=int, default=240)
    p_rc.add_argument(
        "--timeline-max-age-sec",
        type=float,
        default=-1.0,
        help="Drop timeline events older than this many seconds (-1 = no age filter)",
    )
    p_rc.add_argument("--drift-max-entries", type=int, default=48)
    p_rc.add_argument(
        "--drift-max-age-sec",
        type=float,
        default=-1.0,
        help="Drop drift snapshots older than this many seconds (-1 = no age filter)",
    )
    p_rc.add_argument("--event-history-max-entries", type=int, default=120)
    p_rc.add_argument(
        "--event-history-max-age-sec",
        type=float,
        default=-1.0,
        help="Drop event_history rows older than this many seconds (-1 = no age filter)",
    )
    p_rc.set_defaults(func=cmd_runtime_compact_state)

    p_hc = sub.add_parser("healthcheck", help="Run docker/healthcheck.py (local validation + DB ping)")
    p_hc.set_defaults(func=cmd_healthcheck)

    p_rh = sub.add_parser("runtime-health", help="DB + Redis + queue readiness snapshot (exits 1 if not ok)")
    p_rh.set_defaults(func=cmd_runtime_health)

    p_qp = sub.add_parser("queue-pressure", help="Queue depth / lag / inflight sample + saturation warnings")
    p_qp.add_argument("--kind", required=True, help="ingest|ai|publisher")
    p_qp.set_defaults(func=cmd_queue_pressure)

    p_wqs = sub.add_parser("worker-queue-snapshot", help="Per-kind depths, pressure samples, DLQ head (Redis or memory)")
    p_wqs.set_defaults(func=cmd_worker_queue_snapshot)

    p_dl = sub.add_parser("dlq-list", help="List dead-letter records for a job kind (newest first)")
    p_dl.add_argument("--kind", required=True, help="ingest|ai|publisher")
    p_dl.add_argument("--limit", type=int, default=30)
    p_dl.set_defaults(func=cmd_dlq_list)

    p_di = sub.add_parser("dlq-inspect", help="Inspect one DLQ record by index (from dlq-list order)")
    p_di.add_argument("--kind", required=True, help="ingest|ai|publisher")
    p_di.add_argument("--index", type=int, required=True)
    p_di.add_argument("--original-max-chars", type=int, default=4000)
    p_di.set_defaults(func=cmd_dlq_inspect)

    p_dr = sub.add_parser("dlq-replay", help="Remove DLQ entry by index and re-enqueue original job")
    p_dr.add_argument("--kind", required=True, help="ingest|ai|publisher")
    p_dr.add_argument("--index", type=int, required=True)
    p_dr.set_defaults(func=cmd_dlq_replay)

    p_rs = sub.add_parser("retry-stats", help="Print metrics counters related to retries/failures (best-effort)")
    p_rs.set_defaults(func=cmd_retry_stats)

    p_ai = sub.add_parser("ai-analytics", help="AI governance counters (tokens, costs, cluster calls)")
    p_ai.set_defaults(func=cmd_ai_analytics)

    p_ts = sub.add_parser("topic-stats", help="Topic memory file snapshot (counts, hints, fingerprints tail)")
    p_ts.add_argument("--limit", type=int, default=48)
    p_ts.set_defaults(func=cmd_topic_stats)

    p_ei = sub.add_parser("event-inspect", help="Rolling event history excerpts (fingerprint continuity)")
    p_ei.add_argument("--limit", type=int, default=48)
    p_ei.set_defaults(func=cmd_event_inspect)

    p_tr = sub.add_parser("trend-report", help="Burst / momentum heuristics from topic_memory.json")
    p_tr.set_defaults(func=cmd_trend_report)

    p_fb = sub.add_parser("editorial-feedback-report", help="DB aggregates for approve/reject / edit signals")
    p_fb.set_defaults(func=cmd_editorial_feedback_report)

    p_rd = sub.add_parser("relevance-debug", help="Print explainable relevance breakdown for a synthetic cluster")
    p_rd.add_argument(
        "--text",
        default="Bitcoin and Ethereum moved in USA markets after OpenAI announced a new AI product.",
        help="Sample combined text",
    )
    p_rd.add_argument("--channels", default="wire_a,wire_b", help="Comma-separated channel_name values")
    p_rd.add_argument("--evolution", choices=("new", "update", "ambiguous"), default="new")
    p_rd.add_argument("--continuity", type=float, default=0.15, help="EventEvolution.continuity_score 0-1")
    p_rd.add_argument("--topic-hint", default="crypto ai markets", help="Synthetic topic_memory row hint")
    p_rd.add_argument("--topic-count", type=int, default=3, help="Synthetic topic hit count")
    p_rd.add_argument(
        "--duplicate-pct",
        type=float,
        default=-1.0,
        help="Optional max similarity to recent drafts (0-100); pass -1 to omit",
    )
    p_rd.set_defaults(func=cmd_relevance_debug)

    p_ir = sub.add_parser("export-intelligence-report", help="Write editorial intelligence bundle (JSON/HTML)")
    p_ir.add_argument("--out", required=True)
    p_ir.add_argument("--format", choices=("json", "html"), default="json")
    p_ir.set_defaults(func=cmd_export_intelligence_report)

    p_pd = sub.add_parser("policy-debug", help="Resolved ChannelEditorialPolicy for a source channel key")
    p_pd.add_argument("--channel", default="", help="Normalized channel name (default: first SOURCE_CHANNELS)")
    p_pd.set_defaults(func=cmd_policy_debug)

    p_cad = sub.add_parser("cadence-report", help="publish_cadence.json + duplicate burst counter")
    p_cad.set_defaults(func=cmd_cadence_report)

    p_supr = sub.add_parser("suppression-report", help="suppression_state.json + duplicate burst counter")
    p_supr.set_defaults(func=cmd_suppression_report)

    p_tsat = sub.add_parser("topic-saturation-report", help="Topic rows with saturation flag per policy threshold")
    p_tsat.add_argument("--limit", type=int, default=40)
    p_tsat.add_argument("--burst-threshold", type=int, default=8)
    p_tsat.set_defaults(func=cmd_topic_saturation_report)

    p_edrift = sub.add_parser("editorial-drift-report", help="Drift heuristics vs last snapshot (optional DB fetch)")
    p_edrift.add_argument("--no-append", action="store_true", help="Do not append a new snapshot row")
    p_edrift.set_defaults(func=cmd_editorial_drift_report)

    p_pdiv = sub.add_parser("pipeline-decision-inspect", help="Synthetic cluster → unified pipeline decision JSON")
    p_pdiv.add_argument(
        "--text",
        default="Bitcoin and Ethereum moved in USA markets after OpenAI announced a new AI product.",
    )
    p_pdiv.add_argument("--channels", default="wire_a,wire_b")
    p_pdiv.add_argument("--topic-hint", default="crypto markets")
    p_pdiv.add_argument("--fingerprint", default="cli_synthetic_fp")
    p_pdiv.add_argument("--evolution", choices=("new", "update", "ambiguous"), default="new")
    p_pdiv.add_argument("--continuity", type=float, default=0.15)
    p_pdiv.set_defaults(func=cmd_pipeline_decision_inspect)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
