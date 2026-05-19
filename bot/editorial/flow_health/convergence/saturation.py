from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _utc_day() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _maturity_fingerprint(gov: dict[str, Any]) -> str:
    """Deterministic band snapshot — no semantic analysis."""
    parts = [
        str((gov.get("observability") or {}).get("governance_cohesion_status")),
        str((gov.get("observability") or {}).get("observability_integrity_band")),
        str((gov.get("closure") or {}).get("operational_closure_candidate")),
        str((gov.get("legacy") or {}).get("institutional_transferability_band")),
        str((gov.get("minimalism") or {}).get("architectural_compression_band")),
        str((gov.get("doctrine") or {}).get("doctrine_alignment_status")),
        str((gov.get("closure") or {}).get("expansion_pressure_detected")),
    ]
    return "|".join(parts)


def compute_stewardship_novelty_decay(
    *,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """High decay = low new operational signal from maturity layers."""
    gov = governance or {}
    fp = _maturity_fingerprint(gov)
    today = _utc_day()

    try:
        st = load_state()
        cont = dict(st.get("convergence_continuity") or {})
        fingerprints: dict[str, str] = dict(cont.get("maturity_fingerprints") or {})
        prev_fp = fingerprints.get(today)
        yesterday_keys = sorted(fingerprints.keys())
        yesterday_fp = fingerprints.get(yesterday_keys[-2]) if len(yesterday_keys) >= 2 else None

        fingerprints[today] = fp
        keys = sorted(fingerprints.keys())[-21:]
        fingerprints = {k: fingerprints[k] for k in keys}

        unchanged_today = prev_fp == fp if prev_fp else False
        unchanged_vs_yesterday = yesterday_fp == fp if yesterday_fp else False

        recent = [fingerprints[k] for k in keys[-7:]]
        stable_week = len(recent) >= 3 and len(set(recent)) <= 2

        decay = 0.35
        if unchanged_vs_yesterday:
            decay += 0.25
        if stable_week:
            decay += 0.2
        if unchanged_today:
            decay += 0.1

        min_g = gov.get("minimalism") or {}
        if min_g.get("invisible_digest_mode"):
            decay += 0.08

        cont["maturity_fingerprints"] = fingerprints
        cont["last_novelty_fingerprint"] = fp
        save_state(metrics={"convergence_continuity": cont})

        decay = round(min(1.0, decay), 3)
        return {
            "stewardship_novelty_decay": decay,
            "maturity_fingerprint": fp,
            "novelty_stable_week": stable_week,
            "novelty_unchanged_vs_prior": unchanged_vs_yesterday,
        }
    except Exception:
        return {
            "stewardship_novelty_decay": 0.4,
            "maturity_fingerprint": fp,
            "novelty_stable_week": False,
            "novelty_unchanged_vs_prior": False,
        }
