"""Environment awareness for release validation decisions."""

from __future__ import annotations

import os
from typing import Literal

ValidationEnvironment = Literal["LOCAL_DEV", "VPS_BURNIN", "PRODUCTION"]


def detect_validation_environment() -> ValidationEnvironment:
    override = os.getenv("VALIDATION_ENVIRONMENT", "").strip().upper()
    if override in {"LOCAL_DEV", "VPS_BURNIN", "PRODUCTION"}:
        return override  # explicit operator override wins

    runtime_profile = os.getenv("NEWSROOM_RUNTIME_PROFILE", "").strip().lower()
    env = os.getenv("ENV", "").strip().lower()
    app_env = os.getenv("APP_ENV", "").strip().lower()
    rollout = os.getenv("CONTROLLED_PUBLIC_ROLLOUT", "").strip().lower() in {"1", "true", "yes", "on"}
    qa_mode = os.getenv("PREPUBLIC_QA_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
    auto_publish = os.getenv("AUTO_PUBLISH_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}

    prod_like = runtime_profile == "vps" or env == "production" or app_env == "production"
    if not prod_like:
        return "LOCAL_DEV"

    # VPS burn-in is production-like infra but still in protected launch phases.
    if qa_mode or not auto_publish or rollout:
        return "VPS_BURNIN"
    return "PRODUCTION"


def observational_policy(environment: ValidationEnvironment) -> dict[str, bool]:
    if environment == "LOCAL_DEV":
        return {"ignore_missing_observational": True, "strict_observational_thresholds": False}
    if environment == "VPS_BURNIN":
        return {"ignore_missing_observational": True, "strict_observational_thresholds": False}
    return {"ignore_missing_observational": False, "strict_observational_thresholds": True}

