"""Lightweight pre-publish quality validation (log-only by default)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from app.editorial.public_format import detect_duplicate_wording
from app.editorial.publish_body_scrubber import scrub_publish_plaintext
from app.editorial.tuning_loader import get_editorial_tuning
from publisher.public_renderer import strip_internal_debug_text

_METADATA_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("json_sources_ru", re.compile(r"источники\s*\(json\)", re.I)),
    ("json_sources_en", re.compile(r"sources\s*\(json\)", re.I)),
    ("json_channel", re.compile(r'\{\s*"channel"\s*:', re.I)),
    ("json_array_leak", re.compile(r'\[\s*\{\s*"channel"', re.I)),
    ("pre_block", re.compile(r"<pre\b", re.I)),
    ("trace_id", re.compile(r"\btrace_id\b", re.I)),
    ("wrapper_exit", re.compile(r"\bwrapper_exit\b", re.I)),
    ("pipeline_fatal", re.compile(r"\bPIPELINE_FATAL\b", re.I)),
    ("pipeline_terms", re.compile(r"\b(PIPELINE_|pipeline_decision|execution_registry)\b", re.I)),
    ("empty_placeholder", re.compile(r"\(\s*empty\s*\)|\.\.\.\s*empty\s*\)", re.I)),
    ("draft_hash", re.compile(r"\bDraft\s*#\d+", re.I)),
)

_MALFORMED_PUNCT = re.compile(r"!{3,}|,{2,}|\?\?+")
_REPEATED_FRAGMENT = re.compile(r"(.{20,}?)\1+", re.DOTALL)


@dataclass(frozen=True)
class PublishQualityGateResult:
    ok: bool
    warnings: tuple[str, ...]
    block_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "warnings": list(self.warnings),
            "block_reasons": list(self.block_reasons),
        }


def publish_quality_gate_strict() -> bool:
    return os.getenv("PUBLISH_QUALITY_GATE_STRICT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _plain_from_html(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    t = re.sub(r"</p>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return scrub_publish_plaintext(strip_internal_debug_text(t))


def _readability(text: str) -> float:
    from app.editorial.public_format import _readability

    return _readability(text)


def _metadata_violations(blob: str) -> list[str]:
    out: list[str] = []
    for name, rx in _METADATA_LEAK_PATTERNS:
        if rx.search(blob):
            out.append(name)
    return out


def evaluate_publish_quality_gate(
    html: str,
    *,
    plain: str | None = None,
) -> PublishQualityGateResult:
    tuning = get_editorial_tuning()
    qg = tuning.quality_gate
    blob = plain if plain is not None else _plain_from_html(html)
    warnings: list[str] = []
    block_reasons: list[str] = []

    meta = _metadata_violations(blob)
    if meta and qg.block_metadata_leak:
        if qg.mode == "block" or publish_quality_gate_strict():
            block_reasons.extend(meta)
        else:
            warnings.extend(meta)

    if qg.block_metadata_leak and not meta:
        for name, rx in _METADATA_LEAK_PATTERNS:
            if rx.search(html or ""):
                hit = name
                if publish_quality_gate_strict():
                    block_reasons.append(hit)
                else:
                    warnings.append(hit)

    read = _readability(blob)
    if read < qg.min_readability and len(blob) > 80:
        warnings.append(f"low_readability:{read}")

    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    if len(lines) >= 2:
        headline = lines[0]
        body = "\n".join(lines[1:])
        if qg.block_duplicate_headline_body and detect_duplicate_wording(headline, body):
            if publish_quality_gate_strict():
                block_reasons.append("duplicate_headline_body")
            else:
                warnings.append("duplicate_headline_body")

    if _MALFORMED_PUNCT.search(blob):
        warnings.append("malformed_punctuation")

    if _REPEATED_FRAGMENT.search(blob[:2000]):
        warnings.append("repeated_fragment")

    if qg.block_empty_tail:
        paras = [p.strip() for p in blob.split("\n\n") if p.strip()]
        if paras and len(paras[-1]) < 4:
            warnings.append("empty_tail")

    ok = not block_reasons
    return PublishQualityGateResult(
        ok=ok,
        warnings=tuple(dict.fromkeys(warnings)),
        block_reasons=tuple(dict.fromkeys(block_reasons)),
    )


def log_publish_quality_gate(
    *,
    draft_id: int | None,
    result: PublishQualityGateResult,
    html_len: int = 0,
) -> None:
    import logging

    logger = logging.getLogger(__name__)
    if result.ok and not result.warnings:
        return
    logger.info(
        "publish_quality_gate %s",
        json.dumps(
            {
                "draft_id": draft_id,
                "ok": result.ok,
                "warnings": list(result.warnings),
                "block_reasons": list(result.block_reasons),
                "strict": publish_quality_gate_strict(),
                "html_len": html_len,
            },
            ensure_ascii=False,
        ),
    )
