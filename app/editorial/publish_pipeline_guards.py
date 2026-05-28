"""Shared pre-send guards: sanitizer, output lock, quality gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import Settings
from app.editorial.public_content_sanitizer import (
    evaluate_public_content_sanitizer,
    log_public_content_leak_blocked,
)
from app.editorial.public_output_lock import enforce_public_output_lock, log_public_output_lock
from app.editorial.publish_quality_gate import (
    evaluate_publish_quality_gate,
    log_publish_quality_gate,
    publish_quality_gate_strict,
)
from app.editorial.minimal_newsroom import public_output_lock_enforce
from utils.metrics import inc

if TYPE_CHECKING:
    pass


def enforce_publish_html_guards(
    html: str,
    *,
    draft_id: int | None,
    settings: Settings | None = None,
) -> None:
    """Run sanitizer, output lock, and quality gate. Raises on strict block."""
    san = evaluate_public_content_sanitizer(html, settings=settings)
    if san.blocked:
        log_public_content_leak_blocked(draft_id=draft_id, result=san, html_len=len(html))
        inc("public_content_leak_blocked_total")
        raise ValueError(f"public_content_leak:{','.join(san.violations)}")

    lock = enforce_public_output_lock(html)
    log_public_output_lock(draft_id=draft_id, html=html, result=lock)
    if lock.blocked and public_output_lock_enforce():
        inc("public_output_lock_blocked_total")
        raise ValueError(f"public_output_lock:{','.join(lock.violations)}")

    qg = evaluate_publish_quality_gate(html)
    log_publish_quality_gate(draft_id=draft_id, result=qg, html_len=len(html))
    if not qg.ok and publish_quality_gate_strict() and qg.block_reasons:
        inc("publish_quality_gate_blocked_total")
        raise ValueError(f"publish_quality_gate:{','.join(qg.block_reasons)}")
