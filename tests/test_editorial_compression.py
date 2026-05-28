from __future__ import annotations

from app.editorial.clustering import cluster_items, cluster_score
from app.editorial.compression import compress_clusters
from app.editorial.compression_pipeline import item_from_text, run_compression_pipeline
from app.editorial.dedup import collapse_topic_duplicates
from app.editorial.story_types import StoryType, label_story_type
from app.publisher.draft_builder import render_hierarchical_draft


def _item(text: str, *, score: float = 0.7, st: str | None = None) -> dict:
    return {
        "text": text,
        "source": "@cb_economics",
        "final_score": score,
        "breaking": 0.2,
        "story_type": st or label_story_type(text),
    }


def test_collapse_cb_control_duplicates():
    a = _item("ЦБ усиливает контроль наличных в банках", score=0.8)
    b = _item("Банки усиливают контроль наличных по требованию регулятора", score=0.65)
    out = collapse_topic_duplicates([a, b])
    assert len(out) == 1
    assert float(out[0]["final_score"]) == 0.8


def test_compress_keeps_top_clusters_and_budget():
    items = [
        _item("СРОЧНО breaking war sanctions central bank", score=0.9, st=StoryType.BREAKING.value),
        _item("Росстат inflation GDP macro data release", score=0.75, st=StoryType.MACRO.value),
        _item("Merz Ukraine geopolitics NATO support package", score=0.72, st=StoryType.GEOPOLITICS.value),
        _item("Bitcoin exchange hack crypto enforcement case", score=0.68, st=StoryType.CRYPTO.value),
        _item("лол фитнес тренер lifestyle meme", score=0.4, st=StoryType.MISC.value),
        _item("School security domestic policy regional", score=0.6, st=StoryType.DOMESTIC.value),
        _item("EU social media regulation platform rules", score=0.58, st=StoryType.DOMESTIC.value),
        _item("Retail chain earnings consumer demand", score=0.57, st=StoryType.FINANCE.value),
    ]
    clusters = cluster_items(items)
    kept = compress_clusters(clusters, max_clusters=3, max_items=7, max_per_cluster=2)
    total = sum(len(c.items) for c in kept)
    assert len(kept) <= 3
    assert total <= 7
    assert all(not c.items or c.items[0].get("final_score", 0) >= 0.55 or c.story_type == StoryType.BREAKING.value for c in kept)
    filler_kept = any("фитнес" in str(it.get("text")) for c in kept for it in c.items)
    assert not filler_kept


def test_hierarchical_render_not_flat():
    from app.editorial.compression import CompressedCluster

    clusters = [
        CompressedCluster(
            items=[_item("BREAKING war escalation", score=0.9, st="breaking")],
            cluster_score=0.9,
            story_type="breaking",
            rank=1,
        ),
        CompressedCluster(
            items=[_item("Macro inflation data", score=0.75, st="macro")],
            cluster_score=0.75,
            story_type="macro",
            rank=2,
        ),
    ]
    body = render_hierarchical_draft(clusters)
    assert "BREAKING" in body
    assert "TOP STORIES" in body
    assert body.index("BREAKING") < body.index("TOP STORIES")


def test_pipeline_end_to_end():
    raw = [
        item_from_text("СРОЧНО: санкции и война, central bank emergency"),
        item_from_text("Росстат опубликовал инфляцию и CPI на 2.1%"),
        item_from_text("лол мем фитнес тренер"),
        item_from_text("ЦБ усиливает контроль наличных в банках"),
        item_from_text("Банки вводят контроль наличных для клиентов по указу регулятора"),
    ]
    items = [x for x in raw if x is not None]
    kept, body = run_compression_pipeline(items)
    assert kept
    assert "•" in body
    assert "фитнес" not in body.lower()
