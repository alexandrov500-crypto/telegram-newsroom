"""Live operator CLI: status, logs, remote worker health (Mac control plane)."""

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

REPO = Path(__file__).resolve().parents[2]


def _base_url() -> str:
    local = os.getenv("NEWSROOM_LOCAL_URL", "http://127.0.0.1:8080").strip().rstrip("/")
    worker = os.getenv("NEWSROOM_WORKER_URL", "").strip().rstrip("/")
    return worker or local


def _ops_headers() -> dict[str, str]:
    tok = os.getenv("OPS_HTTP_TOKEN", "").strip()
    if tok:
        return {"X-Ops-Token": tok}
    return {}


def _http_get(path: str, *, base: str | None = None, timeout: float = 8.0) -> tuple[int, dict[str, Any] | str]:
    url = f"{(base or _base_url()).rstrip('/')}{path}"
    req = urllib.request.Request(url, headers=_ops_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        code = exc.code
    except Exception as exc:
        return 0, str(exc)
    try:
        return code, json.loads(body)
    except json.JSONDecodeError:
        return code, body


def _print_json(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")


def _runtime_dir() -> str:
    return os.getenv("RUNTIME_STATE_DIR", "var/runtime").strip() or "var/runtime"


def cmd_status(args: argparse.Namespace) -> int:
    local_code, local = _http_get("/health")
    worker_url = os.getenv("NEWSROOM_WORKER_URL", "").strip()
    worker_block: dict[str, Any] | None = None
    if worker_url:
        w_code, w_body = _http_get("/health", base=worker_url)
        worker_block = {"url": worker_url, "http_code": w_code, "body": w_body}

    from app.ops.runtime.execution_lease import read_lease
    from app.ops.runtime.node_role import resolve_execution_profile

    try:
        from app.config import load_settings

        settings = load_settings()
        profile = resolve_execution_profile(settings)
        lease = read_lease(settings.runtime_state_dir)
    except Exception as exc:
        profile = None
        lease = None
        settings_err = str(exc)
    else:
        settings_err = None

    out = {
        "local_health": {"http_code": local_code, "body": local},
        "worker_health": worker_block,
        "execution_profile": profile.to_dict() if profile else None,
        "execution_lease": lease.to_dict() if lease else None,
        "settings_error": settings_err,
    }
    if args.json:
        _print_json(out)
        return 0 if local_code == 200 else 1

    print(f"Local  {_base_url()}/health → HTTP {local_code}")
    if isinstance(local, dict):
        print(f"  status={local.get('status')} conflict={local.get('dependencies', {}).get('telegram_api', {}).get('conflict_detected')}")
        rt = local.get("runtime") or {}
        print(f"  uptime_sec={rt.get('uptime_sec')} queue_depth={rt.get('queue_depth')}")
    if worker_block:
        print(f"Worker {worker_block['url']} → HTTP {worker_block['http_code']}")
    if profile:
        print(f"Node role={profile.node_role.value} polling={profile.polling_enabled} scheduler={profile.scheduler_enabled}")
    if lease:
        print(f"Lease owner={lease.owner_id} age_sec={lease.to_dict().get('age_sec')}")
    if settings_err:
        print(f"Config: {settings_err}", file=sys.stderr)
    return 0 if local_code == 200 else 1


def cmd_logs(args: argparse.Namespace) -> int:
    log_path = Path(args.path or os.getenv("NEWSROOM_LOG", "logs/local-run.log"))
    if not log_path.is_file():
        print(f"Log not found: {log_path}", file=sys.stderr)
        return 1
    tail = max(10, int(args.lines or 80))
    try:
        subprocess.run(["tail", "-n", str(tail), str(log_path)], check=False)
    except FileNotFoundError:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        sys.stdout.write("\n".join(lines[-tail:]) + "\n")
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    script = REPO / "deploy" / "timeweb" / "scripts" / "diagnose-no-posts.sh"
    if script.is_file() and not args.json:
        return subprocess.call(["bash", str(script)])
    code, health = _http_get("/health")
    _, ready = _http_get("/ready")
    _, runtime = _http_get("/runtime/status")
    out = {"health": health, "ready": ready, "runtime_status": runtime, "http_codes": {"health": code}}
    if args.json:
        _print_json(out)
    else:
        print("=== /health ===")
        _print_json(health)
        print("=== /runtime/status ===")
        _print_json(runtime)
    return 0 if code == 200 else 1


def cmd_takeover(args: argparse.Namespace) -> int:
    from app.ops.runtime.execution_lease import write_execution_intent

    path = write_execution_intent(_runtime_dir(), role="worker", reason=args.reason or "cli_takeover")
    print(f"Wrote {path}")
    print("Next steps:")
    print("  1. Stop VPS worker:  ssh VPS 'docker stop telegram-newsroom'")
    print("  2. Mac .env:         RUNTIME_NODE_ROLE=worker TELEGRAM_POLLING_ENABLED=true")
    print("  3. Restart:          make mac-start")
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    from app.ops.runtime.execution_lease import write_execution_intent

    write_execution_intent(_runtime_dir(), role="control", reason=args.reason or "cli_release")
    print("Control plane intent set.")
    print("  Mac:  RUNTIME_NODE_ROLE=control TELEGRAM_POLLING_ENABLED=false")
    print("  VPS:  docker compose up -d newsroom  (in deploy/timeweb)")
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    code, body = _http_get("/runtime/status")
    if args.json:
        _print_json(body)
        return 0 if code == 200 else 1
    if isinstance(body, dict):
        q = body.get("queues") or body.get("queue") or body
        _print_json(q)
    else:
        print(body)
    return 0 if code == 200 else 1


def cmd_drafts(args: argparse.Namespace) -> int:
    code, body = _http_get("/ops/search?limit=15")
    if args.json:
        _print_json(body)
        return 0
    print(body if not isinstance(body, dict) else json.dumps(body, indent=2, default=str)[:4000])
    return 0 if code == 200 else 1


def cmd_maintenance(args: argparse.Namespace) -> int:
    from app.reliability.auto_maintenance import (
        auto_maintenance_snapshot,
        disable_auto_maintenance,
        enable_auto_maintenance,
    )

    rd = _runtime_dir()
    action = getattr(args, "maintenance_action", "status")
    if action == "on":
        enable_auto_maintenance(rd, reason=getattr(args, "reason", "") or "cli")
        print("Auto maintenance ON (publish halted, pipeline continues)")
        return 0
    if action == "off":
        disable_auto_maintenance(rd, reason=getattr(args, "reason", "") or "cli")
        print("Auto maintenance OFF")
        return 0
    snap = auto_maintenance_snapshot(rd)
    if args.json:
        _print_json(snap)
    else:
        print(f"active={snap.get('active')} reason={snap.get('reason', '')}")
    return 0


def cmd_newsroom(args: argparse.Namespace) -> int:
    """Human-readable newsroom dashboard (no raw logs)."""
    try:
        from app.config import load_settings
        from app.editorial.operator_dashboard import (
            build_newsroom_dashboard,
            render_newsroom_dashboard_ru,
        )

        settings = load_settings()
        data = build_newsroom_dashboard(settings)
    except Exception as exc:
        print(f"Dashboard error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(data)
    else:
        print(render_newsroom_dashboard_ru(data))
    return 0


def cmd_panel(args: argparse.Namespace) -> int:
    code, body = _http_get("/ops/panel.json")
    if args.json or isinstance(body, dict):
        _print_json(body)
        return 0 if code == 200 else 1
    print(body)
    return 0 if code == 200 else 1


def cmd_pipeline_run(args: argparse.Namespace) -> int:
    import urllib.request

    url = f"{_base_url()}/ops/control/pipeline/run"
    data = json.dumps({"reason": "cli_pipeline_run"}).encode("utf-8")
    headers = {**_ops_headers(), "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            code = resp.getcode()
    except urllib.error.HTTPError as exc:
        code = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"pipeline trigger failed: {exc}", file=sys.stderr)
        print("Hint: run pipeline via worker process or POST /ops/control on worker URL", file=sys.stderr)
        return 1
    if args.json:
        _print_json(body)
    else:
        print(body)
    return 0 if code == 200 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newsroom", description="Telegram newsroom operator CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)
    lg = sub.add_parser("logs")
    lg.add_argument("--path", type=Path, default=None)
    lg.add_argument("-n", "--lines", type=int, default=80)
    lg.set_defaults(func=cmd_logs)
    sub.add_parser("diagnose").set_defaults(func=cmd_diagnose)
    tk = sub.add_parser("takeover")
    tk.add_argument("--reason", default="")
    tk.set_defaults(func=cmd_takeover)
    rl = sub.add_parser("release")
    rl.add_argument("--reason", default="")
    rl.set_defaults(func=cmd_release)
    sub.add_parser("queue").set_defaults(func=cmd_queue)
    sub.add_parser("drafts").set_defaults(func=cmd_drafts)
    sub.add_parser("pipeline-run").set_defaults(func=cmd_pipeline_run)
    sub.add_parser("panel").set_defaults(func=cmd_panel)
    sub.add_parser("newsroom").set_defaults(func=cmd_newsroom)
    m = sub.add_parser("maintenance")
    msub = m.add_subparsers(dest="maintenance_action", required=True)
    msub.add_parser("status").set_defaults(func=cmd_maintenance)
    mon = msub.add_parser("on")
    mon.add_argument("--reason", default="cli")
    mon.set_defaults(func=cmd_maintenance)
    moff = msub.add_parser("off")
    moff.add_argument("--reason", default="cli")
    moff.set_defaults(func=cmd_maintenance)
    return p


def main(argv: list[str] | None = None) -> int:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    argv = list(argv if argv is not None else sys.argv[1:])
    json_out = False
    if "--json" in argv:
        json_out = True
        argv = [a for a in argv if a != "--json"]
    parser = build_parser()
    args = parser.parse_args(argv)
    args.json = json_out
    return int(args.func(args))
