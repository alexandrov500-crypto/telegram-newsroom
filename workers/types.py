"""Typed job identifiers and error classification (transport-agnostic)."""

from __future__ import annotations

from enum import Enum


class JobType(str, Enum):
    INGEST_ARTICLE = "INGEST_ARTICLE"
    PROCESS_CLUSTER = "PROCESS_CLUSTER"
    GENERATE_SUMMARY = "GENERATE_SUMMARY"
    PUBLISH_DRAFT = "PUBLISH_DRAFT"
    GENERATE_PREVIEW = "GENERATE_PREVIEW"


class ErrorClass(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    RATE_LIMITED = "rate_limited"
    EXTERNAL_SERVICE_FAILURE = "external_service_failure"


class StructuredJobError(Exception):
    """Rich failure for dispatcher / retry engine."""

    def __init__(
        self,
        message: str,
        *,
        classification: ErrorClass = ErrorClass.TRANSIENT,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.detail = detail or message
