"""Contract enforcement for release validators."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.observability.release_contract import OBSERVATIONAL_CONTRACT_FIELDS, REQUIRED_CONTRACT_FIELDS
from app.observability.validation_environment import detect_validation_environment
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _names(items: list[dict[str, str]]) -> set[str]:
    return {str(m.get("name") or "").strip() for m in items if str(m.get("name") or "").strip()}


def enforce_contract_usage(
    *,
    source: str,
    required: list[dict[str, str]],
    observational: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    req_names = _names(required)
    obs_names = _names(observational)

    missing_required = sorted(REQUIRED_CONTRACT_FIELDS - req_names)
    if missing_required:
        errors.extend(f"missing_required_field:{n}" for n in missing_required)

    extra_required = sorted(req_names - REQUIRED_CONTRACT_FIELDS)
    if extra_required:
        errors.extend(f"unregistered_required_field:{n}" for n in extra_required)

    extra_observational = sorted(obs_names - OBSERVATIONAL_CONTRACT_FIELDS)
    if extra_observational:
        errors.extend(f"unregistered_observational_field:{n}" for n in extra_observational)

    overlap = sorted(req_names & obs_names)
    if overlap:
        errors.extend(f"field_tag_conflict:{n}" for n in overlap)

    if errors:
        log_event(
            logger,
            "validation_contract_violation_detected",
            source=source,
            errors=errors[:32],
            required_names=sorted(req_names),
            observational_names=sorted(obs_names),
        )
    return errors


def contract_enforcement_should_block() -> bool:
    mode = detect_validation_environment()
    if mode == "PRODUCTION":
        return True
    return os.getenv("VALIDATION_CONTRACT_BLOCK_NON_PROD", "").strip().lower() in {"1", "true", "yes", "on"}


def maybe_raise_on_contract_violation(
    *,
    source: str,
    required: list[dict[str, str]],
    observational: list[dict[str, str]],
) -> list[str]:
    errors = enforce_contract_usage(source=source, required=required, observational=observational)
    if errors and contract_enforcement_should_block():
        raise RuntimeError(f"{source}: validation contract violation: {', '.join(errors[:4])}")
    return errors

