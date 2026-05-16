"""Config-driven editorial policies (JSON + optional env overlay)."""

from __future__ import annotations

import json
from typing import Any

from db.models import RawPost

from app.config import Settings
from editorial.intelligence_store import editorial_policies_path, load_json
from editorial.policy_models import (
    ChannelEditorialPolicy,
    EditorialPolicyBundle,
    merge_policies,
)


def _merge_top_level(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        if k == "channels" and isinstance(out.get("channels"), dict) and isinstance(v, dict):
            merged = dict(out["channels"])
            merged.update(v)
            out["channels"] = merged
        elif k == "default" and isinstance(v, dict) and isinstance(out.get("default"), dict):
            md = dict(out["default"])
            md.update(v)
            out["default"] = md
        else:
            out[k] = v
    return out


def load_editorial_policy_bundle(settings: Settings) -> EditorialPolicyBundle:
    """Load ``editorial_policies.json`` then merge ``settings.editorial_policies_json`` (object)."""
    path = editorial_policies_path(settings.runtime_state_dir)
    data = load_json(path, {"version": 1, "default": {}, "channels": {}})
    env_raw = (getattr(settings, "editorial_policies_json", None) or "").strip()
    if env_raw:
        try:
            env_obj = json.loads(env_raw)
        except json.JSONDecodeError:
            env_obj = None
        if isinstance(env_obj, dict) and env_obj:
            data = _merge_top_level(data, env_obj)
    default = merge_policies(ChannelEditorialPolicy(), data.get("default") or {})
    ch: dict[str, ChannelEditorialPolicy] = {}
    for name, part in (data.get("channels") or {}).items():
        if not isinstance(part, dict):
            continue
        key = str(name).strip().lower()
        if not key:
            continue
        ch[key] = merge_policies(default, part)
    return EditorialPolicyBundle(default_policy=default, channel_policies=ch, schema_version=1)


def dominant_channel_key(posts: list[RawPost]) -> str:
    freq: dict[str, int] = {}
    for p in posts:
        k = str(p.channel_name or "").strip().lower()
        if not k:
            continue
        freq[k] = freq.get(k, 0) + 1
    if not freq:
        return ""
    return max(freq, key=lambda k: freq[k])


def resolve_effective_policy(bundle: EditorialPolicyBundle, channel_key: str) -> tuple[ChannelEditorialPolicy, tuple[str, ...]]:
    ck = str(channel_key or "").strip().lower()
    if ck and ck in bundle.channel_policies:
        return bundle.channel_policies[ck], ("policy:channel_override", ck)
    return bundle.default_policy, ("policy:default",)
