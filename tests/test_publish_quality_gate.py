from __future__ import annotations

import os

from app.editorial.publish_quality_gate import (
    evaluate_publish_quality_gate,
    publish_quality_gate_strict,
)


def test_quality_gate_log_only_allows_low_readability() -> None:
    html = "<b>Short</b>"
    r = evaluate_publish_quality_gate(html)
    assert r.ok or not r.block_reasons


def test_quality_gate_detects_metadata_leak_warning() -> None:
    html = "<b>Title</b>\nИсточники (JSON)\n<pre>[]</pre>"
    r = evaluate_publish_quality_gate(html)
    assert "json_sources_ru" in r.warnings or "json_sources_ru" in r.block_reasons


def test_quality_gate_strict_blocks_metadata(monkeypatch) -> None:
    monkeypatch.setenv("PUBLISH_QUALITY_GATE_STRICT", "true")
    assert publish_quality_gate_strict()
    html = '<b>Title</b>\n{"channel": "@x"}'
    r = evaluate_publish_quality_gate(html)
    assert not r.ok
    assert r.block_reasons
    monkeypatch.delenv("PUBLISH_QUALITY_GATE_STRICT", raising=False)


def test_quality_gate_does_not_block_duplicate_in_log_only(monkeypatch) -> None:
    monkeypatch.delenv("PUBLISH_QUALITY_GATE_STRICT", raising=False)
    plain = "Same headline here\n\nSame headline here and more text for body."
    r = evaluate_publish_quality_gate("<b>x</b>", plain=plain)
    assert "duplicate_headline_body" in r.warnings or r.ok
