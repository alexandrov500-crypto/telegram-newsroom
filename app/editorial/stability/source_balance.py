"""Source type balance — penalize consecutive same-tier sources."""

from __future__ import annotations

from app.editorial.source_tiers import classify_source


def source_type_key(channel: str) -> str:
    tier, _auth = classify_source(channel)
    if tier == 1:
        return "t1_wire"
    if tier == 2:
        return "t2_curated_ru"
    return "t3_signal"


def consecutive_same_type_penalty(
    runtime_dir: str | None,
    channels: list[str],
) -> tuple[float, str]:
    """
    Return (score_delta, reason). -0.12 if same source class as last publish.
    """
    if not channels:
        return 0.0, ""
    from app.editorial.stability.state import load_state, save_state

    data = load_state(runtime_dir)
    recent = list(data.get("recent_source_types") or [])
    cur = source_type_key(channels[0])
    if recent and recent[-1] == cur:
        return -0.12, f"consecutive_same_source_type:{cur}"
    recent.append(cur)
    data["recent_source_types"] = recent[-16:]
    save_state(runtime_dir, data)
    return 0.0, ""


def record_publish_source_types(runtime_dir: str | None, channels: list[str]) -> None:
    from app.editorial.stability.state import load_state, save_state

    if not channels:
        return
    data = load_state(runtime_dir)
    recent = list(data.get("recent_source_types") or [])
    recent.append(source_type_key(channels[0]))
    data["recent_source_types"] = recent[-16:]
    save_state(runtime_dir, data)
