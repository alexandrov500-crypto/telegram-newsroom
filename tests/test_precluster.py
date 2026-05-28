from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db.models import RawPost
from scheduler.precluster import avg_pairwise_lexical_cohesion, select_cluster_for_summarization


def _post(pid: int, text: str, *, offset_min: int = 0) -> RawPost:
    base = datetime(2026, 5, 23, 14, 0, tzinfo=UTC)
    return RawPost(
        id=pid,
        channel_name="@cb_economics",
        message_id=25140 + pid,
        text=text,
        created_at=base + timedelta(minutes=offset_min),
        collected_at=base + timedelta(minutes=offset_min),
        processed_at=None,
    )


APPLE = (
    "Apple удалила из российского App Store 1213 приложений по требованию "
    "Роскомнадзора за 2025 год, говорится в отчёте компании. В Китае за тот же "
    "период было удалено только 196 приложений."
)
INTIM = (
    "Стоимость интимных услуг в Москве выросла после отключения горячей воды. "
    "Московские проститутки просят заплатить больше или отказываются выезжать "
    "к клиентам, если в их квартире нет горячей воды."
)


def test_unrelated_same_bucket_does_not_merge_both() -> None:
    posts = [_post(1, INTIM, offset_min=0), _post(2, APPLE, offset_min=1)]
    cluster = select_cluster_for_summarization(
        posts,
        bucket_hours=6,
        max_posts=8,
        min_posts_fallback=3,
        min_lexical_jaccard=0.08,
    )
    assert len(cluster) == 1
    assert avg_pairwise_lexical_cohesion(cluster) == 1.0


def test_related_posts_still_cluster() -> None:
    a = (
        "Центральный банк повысил ключевую ставку до 21 процентов с завтрашнего дня "
        "из-за инфляционных рисков и слабого рубля."
    )
    b = (
        "Центральный банк подтвердил повышение ключевой ставки до 21 процентов "
        "и назвал инфляционные риски главной причиной решения."
    )
    posts = [_post(10, a, offset_min=0), _post(11, b, offset_min=2)]
    cluster = select_cluster_for_summarization(
        posts,
        bucket_hours=6,
        max_posts=8,
        min_posts_fallback=3,
        min_lexical_jaccard=0.08,
    )
    assert len(cluster) == 2
    assert avg_pairwise_lexical_cohesion(cluster) >= 0.08
