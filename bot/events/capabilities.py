from __future__ import annotations

from dataclasses import dataclass

CURRENT_NODE_CAPABILITY_VERSION = 1


@dataclass(frozen=True, slots=True)
class NodeCapabilities:
    """Rolling-upgrade safe capability negotiation."""

    node_id: str
    role: str
    envelope_version: int = CURRENT_NODE_CAPABILITY_VERSION
    stream_backend: str = "inmemory"
    supports_replay: bool = True
    supports_idempotent_publish: bool = True

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "envelope_version": self.envelope_version,
            "stream_backend": self.stream_backend,
            "supports_replay": self.supports_replay,
            "supports_idempotent_publish": self.supports_idempotent_publish,
        }

    def compatible_with(self, other: NodeCapabilities) -> bool:
        return (
            self.envelope_version == other.envelope_version
            or abs(self.envelope_version - other.envelope_version) <= 1
        )
