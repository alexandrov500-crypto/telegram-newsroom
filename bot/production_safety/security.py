from __future__ import annotations

import logging
import re
from typing import Any

from bot.production_safety.repository import ProductionSafetyRepository

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"system\s*:\s*you\s+are", re.I),
    re.compile(r"<\s*script", re.I),
)


class ProductionSecurityLayer:
    """RBAC audit, prompt-injection heuristics, publish authorization checks."""

    def __init__(self, repository: ProductionSafetyRepository) -> None:
        self._repo = repository

    def audit_command(
        self,
        operator_id: str,
        command: str,
        *,
        args_preview: str = "",
        success: bool = True,
    ) -> None:
        self._repo.audit_command(
            operator_id=str(operator_id),
            command=command,
            args_preview=args_preview,
            success=success,
        )
        self._repo.operator_heartbeat(str(operator_id), command=command)

    def filter_untrusted_prompt(self, text: str) -> tuple[bool, str | None]:
        for pat in _INJECTION_PATTERNS:
            if pat.search(text):
                return False, "prompt_injection_pattern"
        return True, None

    def validate_publish_authorization(
        self,
        *,
        operator_id: int | None,
        operator_approved: bool,
        admin_ids: frozenset[int],
    ) -> tuple[bool, str]:
        if operator_approved and operator_id is not None and operator_id in admin_ids:
            return True, "admin_approved"
        if operator_approved:
            return False, "approval_requires_admin_operator"
        return False, "not_authorized"
