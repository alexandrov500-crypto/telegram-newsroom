from __future__ import annotations

from app.publisher.draft_builder import (
    complete_story_text,
    format_single_source_draft,
    polish_channel_post,
    render_hierarchical_draft,
    strip_telegram_markdown,
    _one_line_summary,
)
from app.editorial.compression import CompressedCluster


HARVARD_RAW = (
    "[@DeCenter] **🏫 Инвестфонд Гарварда **продолжает [выходить](https://example.com/x) "
    "из крипты — **сократил долю в Bitcoin ETF от BlackRock ещё на 43% и полностью вышел "
    "из Ethereum ETF**. Но пока Гарвард снижает риск, **фонд Абу-Даби Mubadala наоборот "
    "докупает IBIT почти до $566 млн** — крупные деньги явно смотрят на рынок по-разному."
)


def test_strip_telegram_markdown():
    plain = strip_telegram_markdown(HARVARD_RAW)
    assert "**" not in plain
    assert "](http" not in plain
    assert "выходить" in plain
    assert "Гарварда" in plain
    assert not plain.startswith("@DeCenter")


def test_one_line_not_cut_mid_word_at_220():
    plain = strip_telegram_markdown(HARVARD_RAW)
    summary = _one_line_summary(plain, max_len=480)
    assert not summary.endswith("по-разном...")
    assert "Mubadala" in summary or "566" in summary


def test_complete_story_keeps_full_short_text():
    plain = strip_telegram_markdown(HARVARD_RAW)
    out = complete_story_text(plain, max_chars=500)
    assert out.endswith("по-разному.")
    assert "…" not in out


def test_single_source_draft_full_story():
    body = format_single_source_draft(
        {"text": HARVARD_RAW, "source": "@DeCenter"},
        max_chars=3500,
    )
    assert "@DeCenter" not in body
    assert "Harvard" in body or "Гарварда" in body
    assert "Mubadala" in body
    assert "**" not in body
    assert "по-разном..." not in body


def test_polish_strips_channel_bullets_and_completes() -> None:
    raw = (
        "• [@cb_economics] Стоимость интимных услуг в Москве выросла после отключения "
        "горячей воды. Московские проститутки просят заплатить больше...\n"
        "• [@cb_economics] Apple удалила из российского App Store 1213 приложений."
    )
    out = polish_channel_post(raw, max_chars=2000)
    assert "[@cb" not in out
    assert "•" not in out
    assert "Apple" in out
    assert out.count("...") == 0 or out.endswith(".")


def test_hierarchical_single_cluster_uses_blurb():
    c = CompressedCluster(
        items=[{"text": HARVARD_RAW, "source": "@DeCenter", "final_score": 0.8}],
        cluster_score=0.8,
        story_type="crypto",
    )
    body = render_hierarchical_draft([c])
    assert "@DeCenter" not in body
    assert "566" in body
