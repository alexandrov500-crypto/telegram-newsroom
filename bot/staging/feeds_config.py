from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PATH = _PROJECT_ROOT / "config" / "feeds.staging.yaml"


@dataclass(frozen=True)
class StagingFeedEntry:
    name: str
    url: str
    language: str = "en"
    trust: str = "medium"
    noisy: bool = False


def _parse_simple_yaml(path: Path) -> dict:
    """Minimal YAML parser for staging feed catalog (no external deps)."""
    try:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        pass
    text = path.read_text(encoding="utf-8")
    feeds: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "feeds:":
            continue
        if stripped.startswith("- name:"):
            if current:
                feeds.append(current)
            current = {"name": stripped.split(":", 1)[1].strip()}
            continue
        if current is not None and ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val in ("true", "false"):
                current[key] = val == "true"
            else:
                current[key] = val
    if current:
        feeds.append(current)
    return {"feeds": feeds}


def load_staging_feed_catalog(path: Path | str | None = None) -> dict[str, str]:
    """Return source_name → feed_url from staging catalog file."""
    p = Path(path) if path else _DEFAULT_PATH
    if not p.is_file():
        logger.warning("event=staging_feeds_missing path=%s", p)
        return {}
    try:
        data = _parse_simple_yaml(p)
    except OSError as exc:
        logger.warning("event=staging_feeds_read_failed path=%s error=%s", p, exc)
        return {}
    entries = _entries_from_data(data)
    return {e.name: e.url for e in entries}


def _entries_from_data(data: object) -> list[StagingFeedEntry]:
    if not isinstance(data, dict):
        return []
    raw = data.get("feeds")
    if not isinstance(raw, list):
        return []
    out: list[StagingFeedEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if not name or not url:
            continue
        out.append(
            StagingFeedEntry(
                name=name,
                url=url,
                language=str(item.get("language", "en")),
                trust=str(item.get("trust", "medium")),
                noisy=bool(item.get("noisy", False)),
            )
        )
    return out


def resolve_staging_feed_urls(
    *,
    catalog_path: Path | str | None = None,
    env_feeds: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Merge YAML catalog URLs with RSS_FEEDS env overrides (deduped, order preserved)."""
    catalog = load_staging_feed_catalog(catalog_path)
    seen: set[str] = set()
    ordered: list[str] = []
    for url in list(catalog.values()) + list(env_feeds):
        u = url.strip()
        if not u or u in seen:
            continue
        seen.add(u)
        ordered.append(u)
    return tuple(ordered)


def catalog_for_validation(catalog_path: Path | str | None = None) -> dict[str, str]:
    """Alias used by feed validation layer."""
    return load_staging_feed_catalog(catalog_path)
