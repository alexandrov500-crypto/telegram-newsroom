from __future__ import annotations

from pathlib import Path

from bot.ops_certification.certification.engine import ProductionCertificationEngine
from bot.ops_certification.chaos.scheduler import ChaosDrillScheduler
from bot.ops_certification.chaos.scenarios import ChaosDrillRunner
from bot.ops_certification.coordinator import OpsCertificationCoordinator
from bot.ops_certification.governance.controller import GovernanceController
from bot.ops_certification.incidents.workflows import IncidentWorkflowEngine
from bot.ops_certification.longevity.month_uptime import LongevityProtector
from bot.ops_certification.mesh.regional import RegionalMeshFoundation
from bot.ops_certification.reporting.executive import ExecutiveReportGenerator
from bot.ops_certification.repository import OpsCertificationRepository
from bot.ops_certification.security.audit_chain import ImmutableAuditChain, SecurityPostureMonitor
from bot.ops_certification.settings import OpsCertificationSettings
from bot.ops_certification.slo.engine import SloEngine


def build_ops_certification(
    db_path: Path,
    *,
    node_id: str = "local",
    region: str = "global",
) -> OpsCertificationCoordinator:
    settings = OpsCertificationSettings.from_env()
    repo = OpsCertificationRepository(db_path)
    chaos = ChaosDrillRunner()
    return OpsCertificationCoordinator(
        settings=settings,
        repository=repo,
        slo=SloEngine(),
        certification=ProductionCertificationEngine(
            min_score=settings.certification_min_score,
            window_hours=settings.certification_window_hours,
        ),
        chaos=chaos,
        chaos_scheduler=ChaosDrillScheduler(chaos),
        audit=ImmutableAuditChain(repo),
        security=SecurityPostureMonitor(),
        incidents=IncidentWorkflowEngine(),
        longevity=LongevityProtector(),
        governance=GovernanceController(repo),
        mesh=RegionalMeshFoundation(local_node_id=node_id, local_region=region),
        reporting=ExecutiveReportGenerator(repo),
    )
