from __future__ import annotations

from bot.ops_certification.coordinator import OpsCertificationCoordinator

_ops_cert: OpsCertificationCoordinator | None = None


def install_ops_certification(coordinator: OpsCertificationCoordinator | None) -> None:
    global _ops_cert
    _ops_cert = coordinator


def get_ops_certification() -> OpsCertificationCoordinator | None:
    return _ops_cert
