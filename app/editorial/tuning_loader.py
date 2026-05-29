"""Load editorial_tuning.yaml with safe defaults and in-process cache."""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_cached: EditorialTuning | None = None

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "editorial_tuning.yaml"


@dataclass(frozen=True)
class VoiceTuning:
    profile: str
    max_sensational_hits: int
    strip_tabloid: bool


@dataclass(frozen=True)
class StructureTuning:
    headline_max_chars: int
    summary_max_lines: int
    summary_max_chars: int
    include_why_it_matters: bool
    include_cta: bool
    paragraph_spacing: str


@dataclass(frozen=True)
class AttributionTuning:
    style: str
    tier1_compact: bool
    never_show_json: bool


@dataclass(frozen=True)
class QualityGateTuning:
    mode: str
    min_readability: float
    block_duplicate_headline_body: bool
    block_metadata_leak: bool
    block_empty_tail: bool


@dataclass(frozen=True)
class EditorialTuning:
    voice: VoiceTuning
    structure: StructureTuning
    attribution: AttributionTuning
    quality_gate: QualityGateTuning


def _defaults() -> EditorialTuning:
    return EditorialTuning(
        voice=VoiceTuning(
            profile="neutral_professional",
            max_sensational_hits=1,
            strip_tabloid=True,
        ),
        structure=StructureTuning(
            headline_max_chars=140,
            summary_max_lines=6,
            summary_max_chars=3200,
            include_why_it_matters=True,
            include_cta=False,
            paragraph_spacing="double",
        ),
        attribution=AttributionTuning(
            style="source",
            tier1_compact=True,
            never_show_json=True,
        ),
        quality_gate=QualityGateTuning(
            mode="log_only",
            min_readability=0.35,
            block_duplicate_headline_body=True,
            block_metadata_leak=True,
            block_empty_tail=True,
        ),
    )


def _coerce_bool(val: Any, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _merge_section(raw: dict[str, Any] | None, defaults: dict[str, Any]) -> dict[str, Any]:
    out = dict(defaults)
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in defaults:
                out[k] = v
    return out


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse flat nested YAML (scalars only) without external deps."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        if not key:
            continue
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        cur = stack[-1][1]
        if not val.strip():
            child: dict[str, Any] = {}
            cur[key] = child
            stack.append((indent, child))
            continue
        v = val.strip()
        if v.lower() in {"true", "false"}:
            cur[key] = v.lower() == "true"
        elif re.match(r"^-?\d+$", v):
            cur[key] = int(v)
        elif re.match(r"^-?\d+\.\d+$", v):
            cur[key] = float(v)
        else:
            cur[key] = v.strip("\"'")
    return root


def _parse_yaml(path: Path) -> EditorialTuning | None:
    if not path.is_file():
        return None
    try:
        data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not isinstance(data, dict):
        return None
    base = _defaults()
    voice_raw = _merge_section(
        data.get("voice"),
        {
            "profile": base.voice.profile,
            "max_sensational_hits": base.voice.max_sensational_hits,
            "strip_tabloid": base.voice.strip_tabloid,
        },
    )
    struct_raw = _merge_section(
        data.get("structure"),
        {
            "headline_max_chars": base.structure.headline_max_chars,
            "summary_max_lines": base.structure.summary_max_lines,
            "summary_max_chars": base.structure.summary_max_chars,
            "include_why_it_matters": base.structure.include_why_it_matters,
            "include_cta": base.structure.include_cta,
            "paragraph_spacing": base.structure.paragraph_spacing,
        },
    )
    attr_raw = _merge_section(
        data.get("attribution"),
        {
            "style": base.attribution.style,
            "tier1_compact": base.attribution.tier1_compact,
            "never_show_json": base.attribution.never_show_json,
        },
    )
    qg_raw = _merge_section(
        data.get("quality_gate"),
        {
            "mode": base.quality_gate.mode,
            "min_readability": base.quality_gate.min_readability,
            "block_duplicate_headline_body": base.quality_gate.block_duplicate_headline_body,
            "block_metadata_leak": base.quality_gate.block_metadata_leak,
            "block_empty_tail": base.quality_gate.block_empty_tail,
        },
    )
    return EditorialTuning(
        voice=VoiceTuning(
            profile=str(voice_raw["profile"]),
            max_sensational_hits=max(0, int(voice_raw["max_sensational_hits"])),
            strip_tabloid=_coerce_bool(voice_raw["strip_tabloid"], True),
        ),
        structure=StructureTuning(
            headline_max_chars=max(40, min(200, int(struct_raw["headline_max_chars"]))),
            summary_max_lines=max(1, int(struct_raw["summary_max_lines"])),
            summary_max_chars=max(200, int(struct_raw["summary_max_chars"])),
            include_why_it_matters=_coerce_bool(struct_raw["include_why_it_matters"], True),
            include_cta=_coerce_bool(struct_raw["include_cta"], False),
            paragraph_spacing=str(struct_raw["paragraph_spacing"]),
        ),
        attribution=AttributionTuning(
            style=str(attr_raw["style"]).strip().lower(),
            tier1_compact=_coerce_bool(attr_raw["tier1_compact"], True),
            never_show_json=_coerce_bool(attr_raw["never_show_json"], True),
        ),
        quality_gate=QualityGateTuning(
            mode=str(qg_raw["mode"]).strip().lower(),
            min_readability=float(qg_raw["min_readability"]),
            block_duplicate_headline_body=_coerce_bool(qg_raw["block_duplicate_headline_body"], True),
            block_metadata_leak=_coerce_bool(qg_raw["block_metadata_leak"], True),
            block_empty_tail=_coerce_bool(qg_raw["block_empty_tail"], True),
        ),
    )


def editorial_tuning_path() -> Path:
    override = os.getenv("EDITORIAL_TUNING_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_PATH


def load_editorial_tuning(*, reload: bool = False) -> EditorialTuning:
    global _cached
    with _lock:
        if _cached is not None and not reload:
            return _cached
        parsed = _parse_yaml(editorial_tuning_path())
        _cached = parsed if parsed is not None else _defaults()
        return _cached


def get_editorial_tuning() -> EditorialTuning:
    return load_editorial_tuning()
