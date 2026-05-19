from __future__ import annotations

from pathlib import Path

import pytest

from bot.go_live.first_publication import FirstPublicationWorkflow, PublicationStage
from bot.go_live.repository import GoLiveRepository
from bot.go_live.telegram_activation import ChannelPermissions
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> GoLiveRepository:
    init_database(tmp_path / "gl.db")
    return GoLiveRepository(tmp_path / "gl.db")


def test_channel_permissions_all_required() -> None:
    p = ChannelPermissions(
        chat_id=1,
        title="News",
        is_admin=True,
        can_post_messages=True,
        can_edit_messages=True,
        can_delete_messages=True,
        can_invite_users=True,
        can_manage_chat=True,
    )
    assert p.all_required
    assert p.missing() == []


def test_channel_permissions_missing() -> None:
    p = ChannelPermissions(
        chat_id=1,
        title="News",
        is_admin=True,
        can_post_messages=True,
        can_edit_messages=False,
        can_delete_messages=True,
        can_invite_users=True,
        can_manage_chat=True,
    )
    assert not p.all_required
    assert "can_edit_messages" in p.missing()


def test_first_publication_workflow(repo: GoLiveRepository) -> None:
    wf = FirstPublicationWorkflow(repo)
    assert wf.current() == PublicationStage.INTERNAL_SHADOW
    allowed, nxt, gates = wf.evaluate_advance(
        certified=True,
        ga_ready=True,
        confidence=0.9,
        slo_ok=True,
        operator_signoff=True,
    )
    assert allowed
    assert nxt == PublicationStage.SHADOW_TRAFFIC
    stage, _ = wf.advance(
        operator_id="1",
        snapshot={},
        certified=True,
        ga_ready=True,
        confidence=0.9,
    )
    assert stage == PublicationStage.SHADOW_TRAFFIC


def test_publication_rollback(repo: GoLiveRepository) -> None:
    wf = FirstPublicationWorkflow(repo)
    for _ in range(3):
        wf.advance(
            operator_id="1",
            snapshot={},
            certified=True,
            ga_ready=True,
            confidence=0.9,
        )
    target = wf.rollback(operator_id="1", reason="test")
    assert target == PublicationStage.SHADOW_TRAFFIC
