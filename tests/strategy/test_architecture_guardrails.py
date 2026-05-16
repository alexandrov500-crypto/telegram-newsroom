"""Architecture guardrails determinism."""

from __future__ import annotations

from pathlib import Path

from tools.architecture_guardrails import run_guardrails

REPO = Path(__file__).resolve().parents[2]


def test_guardrails_ok_on_repo() -> None:
    r = run_guardrails(repo=REPO)
    assert r["schema_version"] == 1
    assert r["status"] in ("OK", "WARNING")
    assert not any(f["severity"] == "HIGH" and f["code"] == "missing_strategy_doc" for f in r["findings"])


def test_strategy_docs_complete() -> None:
    r = run_guardrails(repo=REPO)
    missing = [f for f in r["findings"] if f["code"] == "missing_strategy_doc"]
    assert missing == []
