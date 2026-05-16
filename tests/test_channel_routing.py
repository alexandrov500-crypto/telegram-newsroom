from __future__ import annotations

import json

from publisher.routing import route_draft_to_channel
from tests.conftest import minimal_test_settings


def test_route_default_channel() -> None:
    s = minimal_test_settings()
    cid = route_draft_to_channel(s, tags=["#x"], category=None, severity=None, sources=None)
    assert cid == s.target_channel_id


def test_route_by_tag_json() -> None:
    alt = -1009998887777
    rules = json.dumps({"by_tag": {"ai": alt}})
    s = minimal_test_settings(channel_routing_rules_json=rules)
    cid = route_draft_to_channel(s, tags=["#AI"], category=None, severity=None, sources=None)
    assert cid == alt
