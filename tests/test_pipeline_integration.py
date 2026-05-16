from ai.editorial import run_pipeline


def test_pipeline_integration():
    raw_text = """
    OpenAI introduced a new multimodal model today.
    The release includes better reasoning and lower latency.
    """

    result = run_pipeline(raw_text)

    assert result is not None
    assert isinstance(result, dict)

    expected_keys = [
        "summary",
        "quality_score",
    ]

    for key in expected_keys:
        assert key in result
