from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bot.live_ops.canary_mode import CanaryPublisher
from bot.live_ops.channel_settings import ControlledLiveSettings, LiveMode
from bot.live_ops.incident_freeze import IncidentFreeze
from bot.live_ops.operator_override import OperatorOverride
from bot.live_ops.repository import LiveChannelRepository
from bot.live_ops.source_quarantine import SourceQuarantine
from bot.runtime.state import runtime_state


@dataclass(frozen=True)
class LivePublishGuardVerdict:
    allowed: bool
    hold: bool
    route_shadow: bool
    reason: str
    blockers: tuple[str, ...]
    requires_approval: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "hold": self.hold,
            "route_shadow": self.route_shadow,
            "reason": self.reason,
            "blockers": list(self.blockers),
            "requires_approval": self.requires_approval,
        }


class LiveChannelPublishGuard:
    """Pre-publish safety: content heuristics + live mode + freeze/canary."""

    _REPEAT = re.compile(r"(.)\1{4,}")
    _BROKEN_MD = re.compile(r"(\*\*[^*]+$|__[^_]+$|\[.*\]\(\s*\))")

    def __init__(
        self,
        settings: ControlledLiveSettings,
        repository: LiveChannelRepository,
        canary: CanaryPublisher,
        freeze: IncidentFreeze,
        override: OperatorOverride,
        source_quarantine: SourceQuarantine | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.canary = canary
        self.freeze = freeze
        self.override = override
        self.source_quarantine = source_quarantine

    def evaluate(
        self,
        *,
        pending_news_id: int,
        headline: str,
        summary: str,
        source: str,
        topic: str,
        operator_approved: bool,
        quality_score: float,
        trust_score: float,
        channel_id: int | None = None,
        cluster_id: int | None = None,
        tags: list[str] | None = None,
    ) -> LivePublishGuardVerdict:
        blockers: list[str] = []
        mode = self._effective_mode()
        state = self.repository.get_state() or {}

        if state.get("frozen"):
            blockers.append("publishing_frozen")
        if state.get("paused"):
            blockers.append("live_paused")
        if self.freeze.is_in_cooldown(state):
            blockers.append("failure_cooldown")
        if self.override.is_frozen():
            blockers.append("operator_freeze")

        content_blockers = self._content_checks(headline, summary)
        blockers.extend(content_blockers)

        try:
            from bot.editorial.flow_health.diversity import publish_diversity_gate

            div_gate = publish_diversity_gate(
                headline=headline,
                cluster_id=cluster_id,
                source=source,
                tags=tags,
                floor_only=False,
            )
            if not div_gate.get("allowed", True):
                blockers.append(str(div_gate.get("reason", "insufficient_story_distance")))
        except Exception:
            pass

        if quality_score < 0.65:
            blockers.append("quality_low")
        if trust_score < 0.7:
            blockers.append("trust_low")

        try:
            from bot.editorial.flow_health.quality_zones import apply_zone_to_blockers

            blockers, _zone = apply_zone_to_blockers(
                blockers,
                quality_score=quality_score,
                trust_score=trust_score,
            )
        except Exception:
            pass

        if self.source_quarantine is not None:
            q, qmode = self.source_quarantine.is_quarantined(source)
            if q:
                blockers.append(f"source_quarantine_{qmode}")

        if self.settings.allowed_sources and source.strip().lower() not in self.settings.allowed_sources:
            blockers.append("source_not_allowed")

        if mode == LiveMode.SHADOW or runtime_state.shadow_publish_only:
            self._audit(pending_news_id, channel_id, mode.value, True, blockers, "shadow_route")
            return LivePublishGuardVerdict(
                True,
                False,
                True,
                "shadow_mode",
                tuple(blockers),
                False,
            )

        canary_ok, canary_reason = self.canary.allow_publish(
            source=source,
            topic=topic,
            state=state,
        )
        if not canary_ok:
            blockers.append(canary_reason)

        requires_approval = False
        if mode == LiveMode.CANARY and self.settings.mandatory_approval_canary:
            requires_approval = True
        if mode == LiveMode.SUPERVISED_LIVE and self.settings.mandatory_approval_supervised:
            requires_approval = True
        if mode == LiveMode.AUTONOMOUS_LIVE:
            requires_approval = False
        if requires_approval and mode == LiveMode.CANARY:
            try:
                from bot.editorial.flow_health.canary_balance import cadence_aware_requires_approval

                requires_approval = cadence_aware_requires_approval(
                    default_requires=True,
                    operator_approved=operator_approved,
                    publish_confidence=trust_score,
                )
            except Exception:
                pass
        if requires_approval and not operator_approved:
            blockers.append("operator_approval_required")

        high_risk = any(
            b.startswith(("hallucination", "empty_", "broken_", "duplicate", "title_body"))
            for b in blockers
        )
        hold = high_risk and mode != LiveMode.SHADOW

        allowed = len(blockers) == 0
        if not allowed:
            try:
                from bot.editorial.flow_health.funnel import record_funnel

                record_funnel(
                    "QUARANTINED",
                    rejection_reason=blockers[0] if blockers else "guard",
                )
            except Exception:
                pass
        reason = "ok" if allowed else f"live_guard:{blockers[0]}"
        self._audit(
            pending_news_id,
            channel_id,
            mode.value,
            allowed,
            blockers,
            reason,
        )
        return LivePublishGuardVerdict(
            allowed=allowed,
            hold=hold,
            route_shadow=not allowed,
            reason=reason,
            blockers=tuple(blockers),
            requires_approval=requires_approval,
        )

    def _effective_mode(self) -> LiveMode:
        state = self.repository.get_state() or {}
        raw = state.get("live_mode") or self.settings.live_mode.value
        try:
            return LiveMode(str(raw))
        except ValueError:
            return self.settings.live_mode

    def _content_checks(self, headline: str, summary: str) -> list[str]:
        blockers: list[str] = []
        text = f"{headline}\n{summary}".strip()
        if len(text) < 40:
            blockers.append("empty_summary")
        if len(summary.strip()) < 25:
            blockers.append("over_short_summary")
        if self._REPEAT.search(text):
            blockers.append("hallucination_repeated_chars")
        words = text.lower().split()
        if words:
            from collections import Counter

            top = Counter(words).most_common(1)[0]
            if top[1] >= 8 and len(words) < 120:
                blockers.append("hallucination_phrase_loop")
        if self._BROKEN_MD.search(text):
            blockers.append("broken_markdown")
        if "<" in text and ">" in text and "</" not in text:
            blockers.append("malformed_html")
        if headline and summary and headline.strip() == summary.strip()[: len(headline)]:
            if len(summary) - len(headline) < 20:
                blockers.append("title_body_mismatch")
        return blockers

    def _audit(
        self,
        pending_news_id: int,
        channel_id: int | None,
        mode: str,
        passed: bool,
        blockers: list[str],
        reason: str,
    ) -> None:
        self.repository.log_publish(
            pending_news_id=pending_news_id,
            channel_id=channel_id,
            live_mode=mode,
            action="pre_publish",
            passed=passed,
            blockers=blockers,
            detail={"reason": reason},
        )
