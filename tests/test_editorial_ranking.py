from __future__ import annotations

from app.editorial.ranking import score_item
from app.editorial.suppression import should_suppress
from app.publisher.draft_builder import build_draft_body
from app.worker.breaking_injector import should_inject_breaking


def test_breaking_score_high_on_urgent_macro():
    item = {
        "text": "СРОЧНО: ЦБ повысил ключевую ставку, санкции на нефть",
        "source": "@cb_economics",
    }
    s = score_item(item)
    assert s.breaking >= 0.8
    assert s.final_score > 0.5
    assert should_inject_breaking(s) or s.final_score > 0.75


def test_low_relevance_meme():
    item = {"text": "лол мем про крипту подписывайтесь", "source": "@random"}
    s = score_item(item)
    assert s.relevance < 0.25


def test_breaking_draft_max_two_bullets():
    body = build_draft_body(
        "First sentence here. Second sentence follows. Third should not appear as bullet.",
        breaking=True,
        sources=[{"channel": "@x"}],
    )
    assert body.count("•") <= 2
    assert "Third should not" not in body or body.count("•") == 2


def test_suppression_blocks_near_duplicate():
    runtime = "/tmp/newsroom_suppress_test"
    a = {"text": "Bitcoin ETF approval expected by SEC regulators this quarter " * 2}
    b = {"text": "Bitcoin ETF approval expected by SEC regulators this quarter " * 2}
    should_suppress(a, runtime_dir=runtime)
    suppressed, sim = should_suppress(b, runtime_dir=runtime)
    assert suppressed is True
    assert sim > 0.87
