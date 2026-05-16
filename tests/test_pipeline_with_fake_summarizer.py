from ai.editorial import run_pipeline
from ai.summarizer import FakeSummarizer


def test_run_pipeline_with_explicit_fake():
    fake = FakeSummarizer(max_chars=80)
    raw = "x" * 200
    result = run_pipeline(raw, summarizer=fake)

    assert result is not None
    assert isinstance(result, dict)
    assert set(result.keys()) == {"summary", "quality_score"}
    assert result["summary"] == "x" * 80
    assert isinstance(result["quality_score"], dict)
    assert "coherence" in result["quality_score"]


def test_run_pipeline_default_matches_fake_shape():
    result = run_pipeline("Short news line.")

    assert result is not None
    assert result["summary"] == "Short news line."
    assert isinstance(result["quality_score"], dict)
