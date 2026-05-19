from __future__ import annotations

from bot.live_ops.telegram_pilot import PilotPreflightReport, pilot_startup_banner_text


def test_preflight_report_render() -> None:
    r = PilotPreflightReport()
    r.add("BOT_TOKEN valid", True)
    r.add("Public channel", False, "Missing post_messages permission")
    out = r.render()
    assert "PILOT STATUS: NOT READY" in out
    assert "[FAIL] Public channel" in out
    assert "Reason:" in out


def test_preflight_report_ready() -> None:
    r = PilotPreflightReport()
    r.add("BOT_TOKEN valid", True)
    r.add("LIVE_MODE=canary", True)
    assert r.passed
    assert "PILOT STATUS: READY" in r.render()


def test_startup_banner_contains_canary() -> None:
    text = pilot_startup_banner_text()
    assert "CONTROLLED PUBLIC PILOT" in text
    assert "canary" in text.lower() or "Mode" in text
