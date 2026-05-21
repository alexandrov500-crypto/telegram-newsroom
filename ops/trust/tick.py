"""Periodic trust maintenance (heartbeat, bounded)."""

from __future__ import annotations

import time
from typing import Any


def run_trust_tick(settings: Any, *, logger: Any = None) -> dict[str, Any]:
    rd = settings.runtime_state_dir
    from ops.trust.drift_baselines import update_drift_baselines
    from ops.trust.autonomous_validation import run_autonomous_validation

    update_drift_baselines(rd)
    validation = run_autonomous_validation(settings, rd)
    out = {"validation_passed": validation.get("passed")}
    # Daily trust certification at most once per UTC day
    stamp_path = __import__("pathlib").Path(rd) / "trust" / ".last_cert_day"
    today = time.strftime("%Y%m%d", time.gmtime())
    try:
        last = stamp_path.read_text(encoding="utf-8").strip() if stamp_path.is_file() else ""
    except OSError:
        last = ""
    if last != today:
        from ops.trust.trust_certification import generate_trust_certification

        cert = generate_trust_certification(settings, rd)
        out["trust_certified"] = cert.get("aggregate_trusted")
        try:
            stamp_path.parent.mkdir(parents=True, exist_ok=True)
            stamp_path.write_text(today, encoding="utf-8")
        except OSError:
            pass
    return out
