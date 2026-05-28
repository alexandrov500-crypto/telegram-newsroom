from __future__ import annotations

import pytest

from app.ops.priority_router import classify_lane, route_message_event
from app.ops.queues import Lane, init_lane_queues, reset_lane_queues_for_tests, sync_legacy_worker_queues
from app.editorial.ranking import score_item
from app.editorial.scoring_engine import score_story


@pytest.fixture
def ops_queues(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_SINGLETON_DISABLED", "true")
    from app.ops.control_plane.api import enable_fast_lane
    from app.ops.control_plane.state import init_ops_state_store, reset_ops_state_store_for_tests

    reset_ops_state_store_for_tests()
    init_ops_state_store(None)
    enable_fast_lane(reason="test")
    reset_lane_queues_for_tests()
    init_lane_queues(fast_max=4, standard_max=4, slow_max=4)
    sync_legacy_worker_queues()
    yield str(tmp_path / "rt")
    reset_lane_queues_for_tests()
    reset_ops_state_store_for_tests()


def test_classify_fast_on_war_keyword():
    text = "BREAKING: war escalation leads to new sanctions package"
    item = {"text": text, "source": "@cb"}
    rank = score_item(item)
    escore = score_story(text=text, sources=["@cb"])
    d = classify_lane(item, rank=rank, escore=escore)
    assert d.lane == Lane.FAST


def test_route_fast_lane_queue(ops_queues):
    item = {
        "text": "URGENT: central bank emergency rate hike amid war sanctions",
        "source": "@cb_economics",
        "news_id": "fast1",
        "runtime_dir": ops_queues,
        "ingested_at_unix": __import__("time").time(),
    }
    d = route_message_event(item)
    assert d is not None
    assert d.lane == Lane.FAST
    assert not d.dropped

    from app.ops.queues import get_lane_queues

    assert get_lane_queues().fast.size() == 1


def test_meme_rejected_before_route(ops_queues):
    item = {
        "text": "Предложение работы от которого невозможно отказаться",
        "source": "@x",
        "runtime_dir": ops_queues,
    }
    assert route_message_event(item) is None
