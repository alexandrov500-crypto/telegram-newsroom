from __future__ import annotations

import asyncio

import pytest

from app.ai.routing.priority import NewsPriority, score_news
from app.ops.queues import get_lane_queues, init_lane_queues, reset_lane_queues_for_tests, sync_legacy_worker_queues
from app.worker.router import route_item


@pytest.fixture
def lane_queues(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_SINGLETON_DISABLED", "true")
    from app.editorial import suppression as sup
    from app.ops.control_plane.api import enable_fast_lane
    from app.ops.control_plane.state import init_ops_state_store, reset_ops_state_store_for_tests

    reset_ops_state_store_for_tests()
    init_ops_state_store(None)
    enable_fast_lane(reason="test")
    reset_lane_queues_for_tests()
    init_lane_queues(fast_max=2, standard_max=2, slow_max=2)
    sync_legacy_worker_queues()
    rt = str(tmp_path / "rt")
    with sup._lock:
        sup._recent_by_runtime.clear()
    yield rt
    reset_lane_queues_for_tests()
    reset_ops_state_store_for_tests()
    with sup._lock:
        sup._recent_by_runtime.clear()


def test_score_breaking_keywords():
    item = {"text": "BREAKING: urgent attack reported in capital", "source": "@news"}
    assert score_news(item) == NewsPriority.BREAKING


def test_score_high_macro():
    item = {"text": "Росстат опубликовал данные по инфляции и CPI за месяц", "source": "@cb"}
    assert score_news(item) == NewsPriority.HIGH


def test_score_low_meme():
    item = {"text": "лол мем про крипту", "source": "@fun"}
    assert score_news(item) == NewsPriority.LOW


_BREAKING_TEXT = (
    "СРОЧНО BREAKING: санкции и война, central bank emergency rate, oil FX markets"
)


def test_route_breaking_to_queue(lane_queues):
    item = {
        "text": _BREAKING_TEXT,
        "source": "@cb_economics",
        "news_id": "a1",
        "runtime_dir": lane_queues,
    }
    pr = route_item(item)
    assert pr == NewsPriority.BREAKING
    assert get_lane_queues().fast.size() == 1


def test_route_escalates_when_breaking_full(lane_queues):
    for i in range(2):
        route_item(
            {
                "text": _BREAKING_TEXT + f" variant {i}",
                "news_id": f"b{i}",
                "source": "@cb_economics",
                "runtime_dir": lane_queues,
            }
        )
    pr = route_item(
        {
            "text": _BREAKING_TEXT + " — ECB follows with additional FX measures",
            "news_id": "b3",
            "source": "@cb_economics",
            "runtime_dir": lane_queues,
        }
    )
    assert pr in {NewsPriority.BREAKING, NewsPriority.HIGH, NewsPriority.NORMAL}
    assert get_lane_queues().fast.size() == 2


def test_route_drops_when_all_full(lane_queues):
    for i in range(2):
        route_item(
            {
                "text": _BREAKING_TEXT + f" drop {i}",
                "news_id": f"x{i}",
                "source": "@cb_economics",
                "runtime_dir": lane_queues,
            }
        )
    for i in range(2):
        route_item(
            {
                "text": f"Росстат GDP CPI macro central bank inflation data release {i}",
                "news_id": f"h{i}",
                "source": "@cb_economics",
                "runtime_dir": lane_queues,
            }
        )
    route_item(
        {
            "text": "Tesla reported quarterly earnings beat with 18% revenue growth",
            "news_id": "n0",
            "source": "@cb_economics",
            "runtime_dir": lane_queues,
        }
    )
    route_item(
        {
            "text": "Samsung expands semiconductor fab capacity in Vietnam under new policy",
            "news_id": "n1",
            "source": "@vedofon",
            "runtime_dir": lane_queues,
        }
    )
    dropped = route_item({"text": "general overflow unique", "news_id": "drop1", "runtime_dir": lane_queues})
    assert dropped is None
    assert get_lane_queues().standard.size() + get_lane_queues().slow.size() >= 1
