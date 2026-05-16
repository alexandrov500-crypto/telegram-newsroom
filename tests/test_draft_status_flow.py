from __future__ import annotations

import pytest

from db.draft_lifecycle import draft_status_values, is_terminal_status, is_transition_allowed
from db.models import DraftStatus


def test_all_status_values_known() -> None:
    assert DraftStatus.PENDING.value in draft_status_values()
    assert DraftStatus.FAILED.value in draft_status_values()


def test_terminal_only_published_rejected() -> None:
    assert is_terminal_status(DraftStatus.PUBLISHED.value) is True
    assert is_terminal_status(DraftStatus.REJECTED.value) is True
    assert is_terminal_status(DraftStatus.FAILED.value) is False
    assert is_terminal_status(DraftStatus.PENDING.value) is False


@pytest.mark.parametrize(
    ("from_s", "to_s", "expected"),
    [
        (DraftStatus.PENDING.value, DraftStatus.APPROVED.value, True),
        (DraftStatus.PENDING.value, DraftStatus.PUBLISHING.value, True),
        (DraftStatus.PENDING.value, DraftStatus.REJECTED.value, True),
        (DraftStatus.PENDING.value, DraftStatus.PUBLISHED.value, False),
        (DraftStatus.APPROVED.value, DraftStatus.PUBLISHING.value, True),
        (DraftStatus.APPROVED.value, DraftStatus.PENDING.value, True),
        (DraftStatus.PUBLISHING.value, DraftStatus.PUBLISHED.value, True),
        (DraftStatus.PUBLISHING.value, DraftStatus.FAILED.value, True),
        (DraftStatus.FAILED.value, DraftStatus.PENDING.value, True),
        (DraftStatus.FAILED.value, DraftStatus.APPROVED.value, False),
        (DraftStatus.PUBLISHED.value, DraftStatus.PENDING.value, False),
        (DraftStatus.REJECTED.value, DraftStatus.PENDING.value, False),
    ],
)
def test_transition_matrix(from_s: str, to_s: str, expected: bool) -> None:
    assert is_transition_allowed(from_s, to_s) is expected


def test_same_status_always_allowed() -> None:
    for s in draft_status_values():
        assert is_transition_allowed(s, s) is True


def test_repeated_transition_semantics() -> None:
    assert is_transition_allowed(DraftStatus.PENDING.value, DraftStatus.PENDING.value) is True


def test_invalid_pending_to_published() -> None:
    assert is_transition_allowed(DraftStatus.PENDING.value, DraftStatus.PUBLISHED.value) is False
