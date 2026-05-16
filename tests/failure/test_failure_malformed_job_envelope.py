from __future__ import annotations

import json

import pytest

from tests.helpers.failure_injection import MALFORMED_JOB_ENVELOPE
from worker.job_queue import JobEnvelope


def test_job_envelope_from_json_rejects_malformed() -> None:
    with pytest.raises((json.JSONDecodeError, TypeError, KeyError, ValueError)):
        JobEnvelope.from_json(MALFORMED_JOB_ENVELOPE)
