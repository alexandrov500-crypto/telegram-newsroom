from __future__ import annotations

from datetime import datetime, timezone

from db.models import RawPost

from editorial.scoring import compute_editorial_score_card


def _post(hours_old: float, ch: str = "@x") -> RawPost:
    ts = datetime.now(timezone.utc)
    return RawPost(
        id=1,
        channel_name=ch,
        message_id=1,
        text="hello world " * 5,
        created_at=ts,
        collected_at=ts,
        processed_at=None,
    )


def test_editorial_score_card_bounds() -> None:
    card = compute_editorial_score_card(
        draft_text="Short",
        raw_posts=[_post(1.0)],
        quality_scores={"uniqueness_ratio": 0.8, "sources_ratio": 0.7},
        cluster_size=2,
    )
    for v in card.to_dict().values():
        assert 0.0 <= v <= 1.0
