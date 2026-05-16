from __future__ import annotations

from utils.text_hash import normalize_text_for_match, sha256_hex


def test_same_text_same_hash():
    a = sha256_hex("Hello world")
    b = sha256_hex("Hello world")
    assert a == b
    assert len(a) == 64


def test_whitespace_normalization_affects_hash():
    h1 = sha256_hex("foo   bar")
    h2 = sha256_hex("foo bar")
    assert h1 == h2


def test_unicode_stable():
    h = sha256_hex("Новости — день")
    assert len(h) == 64
    assert h == sha256_hex("Новости — день")


def test_emoji_handling_deterministic():
    h = sha256_hex("News 📰 update")
    assert h == sha256_hex("News 📰 update")


def test_empty_string_hash():
    h = sha256_hex("")
    assert len(h) == 64
    assert h == sha256_hex("")


def test_normalize_for_match():
    assert normalize_text_for_match("  A\n\nB\t") == "a b"


def test_dedupe_logic_uses_normalize_consistency():
    from db.repository import draft_should_be_skipped_as_duplicate

    body = "Breaking: test"
    recent = [(body + " ", "wrong-hash-not-equal")]
    skip, reason = draft_should_be_skipped_as_duplicate(
        new_content=body,
        new_hash="different_hash",
        recent=recent,
        similarity_threshold=0.99,
    )
    assert skip is True
    assert "similar" in reason
