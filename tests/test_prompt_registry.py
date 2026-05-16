from __future__ import annotations

from tests.conftest import minimal_test_settings
from ai.prompt_registry import fingerprint_cluster_draft, resolve_cluster_draft_prompt


def test_fingerprint_stable_for_same_settings() -> None:
    s = minimal_test_settings()
    a = fingerprint_cluster_draft(s)
    b = fingerprint_cluster_draft(s)
    assert a == b
    assert len(a) == 64


def test_fingerprint_changes_with_summary_style() -> None:
    s1 = minimal_test_settings(summary_style="neutral")
    s2 = minimal_test_settings(summary_style="analytical")
    assert fingerprint_cluster_draft(s1) != fingerprint_cluster_draft(s2)


def test_resolve_cluster_draft_prompt_shape() -> None:
    s = minimal_test_settings()
    p = resolve_cluster_draft_prompt(s)
    assert p.prompt_id == "cluster_draft_json"
    assert p.prompt_version
    assert p.fingerprint == fingerprint_cluster_draft(s)
