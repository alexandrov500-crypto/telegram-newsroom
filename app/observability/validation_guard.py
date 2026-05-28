"""Guardrails against validation contract drift."""

from __future__ import annotations

from app.observability.release_contract import OBSERVATIONAL_CONTRACT_FIELDS, REQUIRED_CONTRACT_FIELDS


def assert_registered_field(name: str, *, kind: str) -> None:
    field = str(name or "").strip()
    if not field:
        raise AssertionError("empty_metric_name")
    kd = str(kind or "").strip().lower()
    if kd == "required":
        if field not in REQUIRED_CONTRACT_FIELDS:
            raise AssertionError(f"unregistered_required_field:{field}")
        return
    if kd == "observational":
        if field not in OBSERVATIONAL_CONTRACT_FIELDS:
            raise AssertionError(f"unregistered_observational_field:{field}")
        return
    raise AssertionError(f"invalid_metric_kind:{kind}")


def assert_no_required_bypass(required_names: set[str]) -> None:
    missing = sorted(REQUIRED_CONTRACT_FIELDS - set(required_names))
    if missing:
        raise AssertionError(f"missing_required_fields:{','.join(missing)}")


def assert_no_observational_promoted(required_names: set[str]) -> None:
    promoted = sorted(set(required_names) & OBSERVATIONAL_CONTRACT_FIELDS)
    if promoted:
        raise AssertionError(f"observational_promoted_to_required:{','.join(promoted)}")


def validate_metric_registration(name: str, *, kind: str) -> None:
    assert_registered_field(name, kind=kind)


def validate_required_coverage(required_names: set[str]) -> None:
    assert_no_required_bypass(required_names)
    assert_no_observational_promoted(required_names)
