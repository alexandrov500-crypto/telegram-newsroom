from __future__ import annotations

from dataclasses import dataclass

from app.editorial.public_content_sanitizer import (
    evaluate_public_content_sanitizer,
    public_content_sanitizer_strict,
)


@dataclass(frozen=True)
class _Settings:
    public_content_sanitizer_strict: bool = True


def test_strict_blocks_pipeline_leak() -> None:
    html = "<b>Headline</b>\nPIPELINE_DECISION trace_id=abc"
    r = evaluate_public_content_sanitizer(html, settings=_Settings(), strict=True)
    assert r.blocked
    assert "pipeline_terms" in r.violations


def test_non_strict_allows_with_violations_flagged() -> None:
    html = "Quality block: rejected"
    r = evaluate_public_content_sanitizer(html, strict=False)
    assert r.ok
    assert r.violations


def test_settings_strict_flag() -> None:
    assert public_content_sanitizer_strict(_Settings(public_content_sanitizer_strict=True))


def test_strict_blocks_ru_json_sources() -> None:
    html = "<b>Headline</b>\nИсточники (JSON)\n<pre>[]</pre>"
    r = evaluate_public_content_sanitizer(html, settings=_Settings(), strict=True)
    assert r.blocked
    assert "json_sources_ru" in r.violations
