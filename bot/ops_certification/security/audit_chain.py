from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from bot.ops_certification.repository import OpsCertificationRepository

logger = logging.getLogger(__name__)


def _hash_payload(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class SignedOperatorAction:
    action_id: str
    operator_id: str
    command: str
    chain_hash: str
    prev_hash: str


@dataclass
class ImmutableAuditChain:
    """Hash-linked operator audit with optional HMAC signature."""

    repository: OpsCertificationRepository
    _secret: str | None = None

    def __post_init__(self) -> None:
        self._secret = os.getenv("OPS_AUDIT_HMAC_SECRET", "").strip() or None

    def sign_action(
        self,
        operator_id: str,
        command: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> SignedOperatorAction:
        action_id = str(uuid.uuid4())
        prev = self.repository.last_audit_hash()
        body = json.dumps(
            {"operator_id": operator_id, "command": command, "payload": payload or {}},
            sort_keys=True,
        )
        payload_hash = _hash_payload(body)
        chain_input = f"{prev}|{action_id}|{payload_hash}"
        chain_hash = _hash_payload(chain_input)
        signature = None
        if self._secret:
            signature = hmac.new(
                self._secret.encode(),
                chain_hash.encode(),
                hashlib.sha256,
            ).hexdigest()
        self.repository.append_audit_chain(
            action_id=action_id,
            operator_id=operator_id,
            command=command,
            payload_hash=payload_hash,
            prev_hash=prev,
            chain_hash=chain_hash,
            signature=signature,
        )
        return SignedOperatorAction(
            action_id=action_id,
            operator_id=operator_id,
            command=command,
            chain_hash=chain_hash,
            prev_hash=prev,
        )

    def verify_chain(self, action_id: str) -> tuple[bool, str]:
        entry = self.repository.audit_entry(action_id)
        if entry is None:
            return False, "not_found"
        expected_input = f"{entry['prev_hash']}|{entry['action_id']}|{entry['payload_hash']}"
        expected = _hash_payload(expected_input)
        if expected != entry["chain_hash"]:
            return False, "tamper_detected"
        if entry.get("signature") and self._secret:
            sig = hmac.new(
                self._secret.encode(),
                entry["chain_hash"].encode(),
                hashlib.sha256,
            ).hexdigest()
            if sig != entry["signature"]:
                return False, "signature_invalid"
        return True, "ok"

    def trace_text(self, action_id: str) -> str:
        entry = self.repository.audit_entry(action_id)
        if entry is None:
            return f"No audit entry for <code>{action_id}</code>"
        ok, reason = self.verify_chain(action_id)
        lines = [
            f"<b>Audit trace</b> <code>{action_id[:12]}</code>",
            f"Operator: {entry['operator_id']} · cmd {entry['command']}",
            f"Integrity: {'✅' if ok else '⛔'} ({reason})",
            f"Chain: <code>{entry['chain_hash'][:16]}…</code>",
        ]
        return "\n".join(lines)


@dataclass
class SecurityPostureMonitor:
    """Suspicious source scoring and admin anomaly hints."""

    _admin_actions: dict[str, int] = field(default_factory=dict)

    def record_admin_action(self, operator_id: str) -> float:
        self._admin_actions[operator_id] = self._admin_actions.get(operator_id, 0) + 1
        count = self._admin_actions[operator_id]
        if count > 50:
            return 0.3
        if count > 20:
            return 0.6
        return 1.0

    def score_source(self, *, trust: float, misinfo: float, injection: bool) -> float:
        score = trust * (1.0 - misinfo)
        if injection:
            score *= 0.2
        return max(0.0, min(1.0, score))

    def snapshot(self) -> dict[str, Any]:
        return {
            "admin_activity": dict(self._admin_actions),
            "credential_misuse_alerts": 0,
        }
