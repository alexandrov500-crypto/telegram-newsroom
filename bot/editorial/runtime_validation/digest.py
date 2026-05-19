from __future__ import annotations

from typing import Any

MAX_QUIET_DIGEST_LINES = 4
MAX_STEWARDSHIP_SECTION_LINES = 12


def verify_digest_silence(
    *,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Digest silence & verbosity creep — not a scoring engine."""
    ctx = ctx or {}
    line_count = 0
    stewardship_lines = 0
    invisible = False
    ultra_quiet = False
    finalization_quiet = False

    try:
        from bot.editorial.flow_health.signal_compression import format_compressed_digest_html

        lines = format_compressed_digest_html(ctx)
        line_count = len(lines)
        stewardship_lines = sum(1 for ln in lines if ln.startswith("•") or "<b>Operational" in ln)
    except Exception:
        lines = []

    gov = ctx.get("flow_governance") or {}
    min_g = gov.get("minimalism") or ctx.get("flow_minimalism") or {}
    frz = gov.get("freeze_registry") or ctx.get("flow_freeze_registry") or {}
    conv = gov.get("convergence") or ctx.get("flow_convergence") or {}

    invisible = bool(min_g.get("invisible_digest_mode"))
    ultra_quiet = bool(frz.get("ultra_quiet_digest"))
    finalization_quiet = bool(conv.get("finalization_digest_quiet"))

    quiet_expected = invisible or ultra_quiet or finalization_quiet
    noise_drift = 0.0
    if quiet_expected and line_count > MAX_QUIET_DIGEST_LINES:
        noise_drift = round(min(1.0, (line_count - MAX_QUIET_DIGEST_LINES) / 8), 3)

    verbosity_pressure = 0.0
    if stewardship_lines > MAX_STEWARDSHIP_SECTION_LINES:
        verbosity_pressure = round(
            min(1.0, stewardship_lines / (MAX_STEWARDSHIP_SECTION_LINES * 2)),
            3,
        )

    invisible_stable = invisible and line_count <= MAX_QUIET_DIGEST_LINES

    return {
        "digest_line_count": line_count,
        "digest_noise_drift": noise_drift,
        "invisible_digest_stability": invisible_stable,
        "stewardship_verbosity_pressure": verbosity_pressure,
        "digest_silence_ok": quiet_expected and noise_drift < 0.25 or not quiet_expected,
        "quiet_modes": {
            "invisible_digest": invisible,
            "ultra_quiet": ultra_quiet,
            "finalization_quiet": finalization_quiet,
        },
    }
