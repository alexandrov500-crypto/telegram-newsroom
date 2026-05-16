from ai.editorial import run_pipeline


def test_pipeline_smoke():
    text = "OpenAI launched a new AI feature."

    result = run_pipeline(text)

    assert result is not None
    assert "summary" in result
    assert "quality_score" in result
    assert isinstance(result["quality_score"], dict)
    assert "coherence" in result["quality_score"]
