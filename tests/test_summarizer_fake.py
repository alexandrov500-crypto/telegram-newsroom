from ai.summarizer import FakeSummarizer


def test_fake_summarize_returns_str():
    s = FakeSummarizer()
    out = s.summarize("hello world")
    assert isinstance(out, str)
    assert out == "hello world"


def test_fake_summarize_deterministic():
    s = FakeSummarizer()
    text = "alpha beta gamma " * 30
    assert s.summarize(text) == s.summarize(text)
    assert len(s.summarize(text)) <= 200


def test_fake_summarize_empty_input():
    s = FakeSummarizer()
    assert s.summarize("") == ""
    assert s.summarize("   \n\t  ") == ""
