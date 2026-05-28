"""Shared release validation contract (required vs observational metrics)."""

from __future__ import annotations

from typing import Any

from app.observability.release_contract import FinalVerdict
from app.observability.validation_contract_enforcer import maybe_raise_on_contract_violation

VALID_STATES = {"PASS", "FAIL", "UNKNOWN"}


def metric(name: str, state: str, *, reason: str = "", kind: str = "required") -> dict[str, str]:
    st = str(state or "UNKNOWN").upper()
    if st not in VALID_STATES:
        st = "UNKNOWN"
    kd = str(kind or "required").lower()
    if kd not in {"required", "observational"}:
        kd = "required"
    return {"name": name, "kind": kd, "state": st, "reason": reason}


def assert_validation_contract(required: list[dict[str, str]], observational: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    req_names = {m.get("name") for m in required}
    obs_names = {m.get("name") for m in observational}
    for overlap in sorted((req_names & obs_names) - {None}):
        errors.append(f"metric_tag_conflict:{overlap}")
    for bucket_name, bucket in (("required", required), ("observational", observational)):
        for m in bucket:
            state = str(m.get("state") or "").upper()
            if state not in VALID_STATES:
                errors.append(f"invalid_state:{bucket_name}:{m.get('name')}:{state}")
    return errors


def evaluate_release_contract(
    *,
    source: str,
    required: list[dict[str, str]],
    observational: list[dict[str, str]],
    ignore_missing_observational: bool,
) -> dict[str, Any]:
    contract_usage_errors = maybe_raise_on_contract_violation(
        source=source,
        required=required,
        observational=observational,
    )
    contract_errors = assert_validation_contract(required, observational)

    required_failed = [m for m in required if m.get("state") == "FAIL"]
    required_unknown = [m for m in required if m.get("state") == "UNKNOWN"]
    obs_failed = [m for m in observational if m.get("state") == "FAIL"]
    obs_unknown = [m for m in observational if m.get("state") == "UNKNOWN"]

    blockers: list[str] = []
    warnings: list[str] = []
    blockers.extend(contract_usage_errors)
    blockers.extend(contract_errors)
    blockers.extend(f"required_failed:{m['name']}" for m in required_failed)
    blockers.extend(f"required_unknown:{m['name']}" for m in required_unknown)

    if not ignore_missing_observational:
        warnings.extend(f"observational_unknown:{m['name']}" for m in obs_unknown)
    warnings.extend(f"observational_failed:{m['name']}" for m in obs_failed)

    if blockers:
        verdict = FinalVerdict.NOT_READY.value
    elif warnings:
        verdict = FinalVerdict.CONDITIONAL.value
    else:
        verdict = FinalVerdict.READY_FOR_PUBLIC.value

    return {
        "verdict": verdict,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "required": required,
        "observational": observational,
        "required_passed": len([m for m in required if m.get("state") == "PASS"]),
        "required_total": len(required),
        "observational_passed": len([m for m in observational if m.get("state") == "PASS"]),
        "observational_total": len(observational),
    }


def evaluate_required_only_contract(*, required: list[dict[str, str]]) -> dict[str, Any]:
    """Deterministic required-field gate (observational metrics ignored)."""
    from app.observability.release_contract import REQUIRED_CONTRACT_FIELDS

    present = {str(m.get("name") or ""): m for m in required}
    blockers: list[str] = []
    normalized: list[dict[str, str]] = []
    for field_name in sorted(REQUIRED_CONTRACT_FIELDS):
        item = present.get(field_name)
        if not item:
            normalized.append(metric(field_name, "UNKNOWN", reason="required_field_missing"))
            blockers.append(f"required_unknown:{field_name}")
            continue
        normalized.append(item)
        state = str(item.get("state") or "UNKNOWN").upper()
        if state == "FAIL":
            blockers.append(f"required_failed:{field_name}")
        elif state == "UNKNOWN":
            blockers.append(f"required_unknown:{field_name}")

    verdict = (
        FinalVerdict.READY_FOR_PUBLIC.value
        if not blockers
        else FinalVerdict.NOT_READY.value
    )
    return {
        "verdict": verdict,
        "blockers": sorted(set(blockers)),
        "warnings": [],
        "required": normalized,
        "required_passed": len([m for m in normalized if m.get("state") == "PASS"]),
        "required_total": len(REQUIRED_CONTRACT_FIELDS),
    }

