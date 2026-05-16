from __future__ import annotations

from ai.editorial_tags import infer_editorial_tags


def test_infer_editorial_tags_ai_keyword() -> None:
    out = infer_editorial_tags("OpenAI announces GPT-5 for enterprise", [{"channel": "@openai", "message_id": 1}])
    assert out["category"] == "AI"
    assert float(out["category_confidence"]) > 0.3
    assert isinstance(out["inferred_tags"], list)
    assert "#AI" in out["inferred_tags"]


def test_infer_editorial_tags_default_bucket() -> None:
    out = infer_editorial_tags("short text", [])
    assert out["category"] == "Technology"
    assert "technology" in (out.get("category_reasoning") or "").lower()
