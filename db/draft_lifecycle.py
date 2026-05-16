from __future__ import annotations

from db.models import DraftStatus


def draft_status_values() -> frozenset[str]:
    return frozenset(s.value for s in DraftStatus)


def is_terminal_status(status: str) -> bool:
    """Terminal for blocking transitions (FAILED may be reset to PENDING for retry)."""
    return status in (
        DraftStatus.PUBLISHED.value,
        DraftStatus.REJECTED.value,
    )


def is_transition_allowed(from_status: str, to_status: str) -> bool:
    """Deterministic lifecycle rules (string values as stored in DB)."""
    if from_status == to_status:
        return True
    if is_terminal_status(from_status):
        return False

    allowed: dict[str, frozenset[str]] = {
        DraftStatus.PENDING.value: frozenset(
            {
                DraftStatus.APPROVED.value,
                DraftStatus.REJECTED.value,
                DraftStatus.PUBLISHING.value,  # legacy direct claim
            }
        ),
        DraftStatus.APPROVED.value: frozenset(
            {
                DraftStatus.PUBLISHING.value,
                DraftStatus.REJECTED.value,
                DraftStatus.FAILED.value,
                DraftStatus.PENDING.value,  # rollback
            }
        ),
        DraftStatus.PUBLISHING.value: frozenset(
            {
                DraftStatus.PUBLISHED.value,
                DraftStatus.FAILED.value,
                DraftStatus.PENDING.value,  # rollback / dry-run recovery
                DraftStatus.APPROVED.value,
            }
        ),
        DraftStatus.FAILED.value: frozenset(
            {
                DraftStatus.PENDING.value,
            }
        ),
    }
    return to_status in allowed.get(from_status, frozenset())
