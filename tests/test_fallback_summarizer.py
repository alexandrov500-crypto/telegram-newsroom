from __future__ import annotations

from types import SimpleNamespace

from ai.fallback_summarizer import fallback_summarize_cluster


def _post(text: str, *, ch: str = "@cb_economics", mid: int = 1, pid: int = 10) -> SimpleNamespace:
    return SimpleNamespace(id=pid, channel_name=ch, message_id=mid, text=text)


HARVARD = (
    "[@DeCenter] **🏫 Test **продолжает [выходить](https://example.com) из крипты — "
    "длинный текст про ETF и Mubadala до $566 млн — крупные деньги смотрят по-разному."
)


def test_fallback_single_post_plain():
    sc = fallback_summarize_cluster([_post(HARVARD, ch="@DeCenter", mid=99)], max_body_chars=3500)
    assert "**" not in sc.post_text
    assert "](http" not in sc.post_text
    assert "566" in sc.post_text
    assert "@DeCenter" not in sc.post_text
    assert "•" not in sc.post_text


def test_fallback_multi_post_no_raw_markdown():
    posts = [
        _post("Росстат CPI inflation data release for April", pid=1, mid=1),
        _post("Merz comments on NATO support package", ch="@vedofon", pid=2, mid=2),
    ]
    sc = fallback_summarize_cluster(posts, max_body_chars=3500)
    assert "TOP STORIES" not in sc.post_text
    assert "CPI" in sc.post_text or "inflation" in sc.post_text
    assert "Merz" in sc.post_text or "NATO" in sc.post_text
    assert "**" not in sc.post_text
