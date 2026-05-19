from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.cognitive.runtime import CognitiveEditorialRuntime
from bot.epistemic.calibration import HumanTrustCalibration
from bot.epistemic.confidence import ConfidenceInputs, ConfidenceModel, ConfidencePropagation
from bot.epistemic.contradiction import ContradictionGraph
from bot.epistemic.drift import DriftAnalyzer
from bot.epistemic.governance import EpistemicGovernance
from bot.epistemic.misinformation import MisinformationDetector, PropagationSignal
from bot.epistemic.narrative import NarrativeTracker
from bot.epistemic.observability import EpistemicObservability
from bot.epistemic.replay import EpistemicReplayValidator
from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.trust import TrustGraph
from bot.mesh.runtime import FederatedCognitiveMesh

logger = logging.getLogger(__name__)


@dataclass
class EpistemicIntegrityLayer:
    """Trustworthy epistemic infrastructure facade."""

    repository: EpistemicRepository
    confidence: ConfidenceModel
    propagation: ConfidencePropagation
    contradictions: ContradictionGraph
    narrative: NarrativeTracker
    trust: TrustGraph
    misinformation: MisinformationDetector
    replay: EpistemicReplayValidator
    drift: DriftAnalyzer
    calibration: HumanTrustCalibration
    governance: EpistemicGovernance
    observability: EpistemicObservability
    mesh: FederatedCognitiveMesh | None
    cognitive: CognitiveEditorialRuntime
    node_id: str
    region: str

    async def tick(
        self,
        *,
        mesh_health: float = 1.0,
        queue_backlog: int = 0,
        apply_checks: bool = True,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {"integrity_checks": 0}

        if self.mesh is not None:
            memory_shards = self.mesh.repository.recent_events(region=self.region, limit=5)
            for ev in memory_shards:
                if ev.get("event_type") == "agent.evaluation_shared":
                    import json

                    try:
                        payload = json.loads(ev["payload_json"])
                        score_val = float(payload.get("score", 0.5))
                        self.confidence.score(
                            "evaluation",
                            str(payload.get("target_id", "unknown")),
                            ConfidenceInputs(base_score=score_val, evidence_count=1),
                        )
                        report["integrity_checks"] = int(report.get("integrity_checks", 0)) + 1
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass

        open_contra = self.contradictions.open_contradictions(limit=5)
        report["open_contradictions"] = len(open_contra)

        drift_report = self.drift.analyze_overconfident_routing([0.85, 0.9, 0.88], region=self.region)
        if drift_report.alert:
            report["drift_alert"] = drift_report.drift_kind

        burst = min(10.0, queue_backlog / 50.0)
        alert = self.misinformation.analyze(
            f"backlog:{queue_backlog}",
            PropagationSignal(
                source_count=2,
                burst_rate=burst,
                diversity_score=0.5,
                narrative_anomaly=0.0,
                replay_seen=False,
            ),
        )
        if alert:
            report["misinformation_alert"] = alert.alert_id

        snap = self.observability.build_snapshot(
            mesh_health=mesh_health,
            regional_confidence={self.region: 1.0 - len(open_contra) * 0.05},
        )
        report["federation_stability"] = snap.federation_stability
        report["misinformation_pressure"] = snap.misinformation_pressure

        try:
            from bot.observability.metrics import set_open_contradictions

            set_open_contradictions(len(open_contra))
        except Exception:
            pass

        return report

    async def score_evaluation(
        self,
        target_id: str,
        *,
        base_score: float,
        source_count: int = 1,
        contradiction_count: int = 0,
    ) -> dict[str, Any]:
        score = self.confidence.score(
            "evaluation",
            target_id,
            ConfidenceInputs(
                base_score=base_score,
                source_count=source_count,
                contradiction_count=contradiction_count,
            ),
        )
        decision = self.governance.validate_score(score)
        return {
            "score": score.to_dict(),
            "governance_allowed": decision.allowed,
            "requires_disclosure": decision.requires_disclosure,
        }

    async def analyze_story(
        self,
        *,
        story_id: int,
        title: str,
        summary: str | None,
        source: str,
        source_count: int = 1,
    ) -> dict[str, Any]:
        narrative = self.narrative.track(
            topic=f"story:{story_id}",
            title=title,
            summary=summary,
            region=self.region,
            source_count=source_count,
        )
        eval_result = await self.cognitive.evaluate_pending(
            target_type="pending_news",
            payload={
                "target_id": str(story_id),
                "title": title,
                "summary": summary or "",
                "source_count": source_count,
                "story_id": story_id,
            },
        )
        scores = [r.get("score", 0.5) for r in eval_result if isinstance(r.get("score"), (int, float))]
        epistemic = self.propagation.aggregate("story", str(story_id), scores) if scores else None

        trust_edge = self.trust.update_from_contradiction(source, contradiction_count=0)
        alert = self.misinformation.analyze(
            str(story_id),
            PropagationSignal(
                source_count=source_count,
                burst_rate=1.0,
                diversity_score=min(1.0, source_count / 3),
                narrative_anomaly=narrative.anomaly_score,
                replay_seen=False,
            ),
        )

        return {
            "narrative": {
                "id": narrative.narrative_id,
                "anomaly": narrative.anomaly_score,
                "framing": list(narrative.framing_tags),
            },
            "epistemic_score": epistemic.to_dict() if epistemic else None,
            "trust": {"score": trust_edge.trust_score, "reason": trust_edge.reason},
            "alert": alert.alert_id if alert else None,
        }


def build_epistemic_integrity_layer(
    db_path: Path,
    cognitive: CognitiveEditorialRuntime,
    *,
    mesh: FederatedCognitiveMesh | None = None,
    node_id: str,
    region: str,
) -> EpistemicIntegrityLayer:
    repo = EpistemicRepository(db_path)
    gov_doc = repo.get_active_governance()
    confidence = ConfidenceModel(repo, gov_doc)
    layer = EpistemicIntegrityLayer(
        repository=repo,
        confidence=confidence,
        propagation=ConfidencePropagation(confidence),
        contradictions=ContradictionGraph(repo),
        narrative=NarrativeTracker(repo),
        trust=TrustGraph(repo),
        misinformation=MisinformationDetector(repo, node_id=node_id, region=region),
        replay=EpistemicReplayValidator(repo, confidence),
        drift=DriftAnalyzer(repo),
        calibration=HumanTrustCalibration(repo, TrustGraph(repo)),
        governance=EpistemicGovernance(repo),
        observability=EpistemicObservability(repo),
        mesh=mesh,
        cognitive=cognitive,
        node_id=node_id,
        region=region,
    )
    logger.info("event=epistemic_integrity_built node_id=%s region=%s", node_id, region)
    return layer
