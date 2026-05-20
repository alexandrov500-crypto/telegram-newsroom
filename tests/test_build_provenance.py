from __future__ import annotations

import os
from unittest.mock import patch

from app.build_provenance import load_build_provenance, version_payload


def test_load_build_provenance_from_env() -> None:
    env = {
        "NEWSROOM_GIT_SHA": "abc1234",
        "NEWSROOM_BUILD_TIMESTAMP": "2026-05-20T12:00:00Z",
        "NEWSROOM_BUILD_BRANCH": "main",
        "NEWSROOM_BUILD_VERSION": "1.0.0",
    }
    with patch.dict(os.environ, env, clear=False):
        prov = load_build_provenance()
    assert prov.git_sha == "abc1234"
    assert prov.build_branch == "main"


def test_version_payload_includes_polling_id() -> None:
    payload = version_payload(polling_instance_id="uuid-test")
    assert payload["polling_instance_id"] == "uuid-test"
    assert "runtime_started_at" in payload
    assert "git_sha" in payload
