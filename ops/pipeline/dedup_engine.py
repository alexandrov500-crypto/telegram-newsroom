"""Two-stage dedup: L1 hash (url/title/body) + L2 lexical similarity."""

from __future__ import annotations

import difflib
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from ops.pipeline.paths import dedup_index_path
from utils.text_hash import normalize_text_for_match

_lock = threading.RLock()
_MAX_INDEX_LINES = 8_000
_DEFAULT_L2_THRESHOLD = 0.88


@dataclass(frozen=True)
class DedupVerdict:
    duplicate: bool
    stage: str  # none | L1 | L2
    matched_key: str = ""
    similarity: float = 0.0
    reason: str = ""


def _content_hash(text: str) -> str:
    norm = normalize_text_for_match(text or "")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def _title_fingerprint(text: str) -> str:
    first = (text or "").strip().split("\n", 1)[0][:200]
    norm = normalize_text_for_match(first)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:24]


def build_ingest_key(source: str, message_id: int, text: str) -> str:
    """Deterministic idempotency key for raw ingest."""
    src = (source or "").strip().lower()
    ch = _content_hash(text)
    raw = f"{src}|{int(message_id)}|{ch}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DedupEngine:
    def __init__(
        self,
        runtime_dir: str | None,
        *,
        l2_threshold: float | None = None,
    ) -> None:
        self._runtime_dir = runtime_dir
        self._l2_threshold = float(
            l2_threshold
            if l2_threshold is not None
            else __import__("os").getenv("OPS_DEDUP_L2_THRESHOLD", str(_DEFAULT_L2_THRESHOLD))
        )

    def check(self, *, source: str, message_id: int, text: str, url: str = "") -> DedupVerdict:
        ingest_key = build_ingest_key(source, message_id, text)
        title_fp = _title_fingerprint(text)
        body_hash = _content_hash(text)
        url_key = ""
        if url.strip():
            url_key = hashlib.sha256(url.strip().lower().encode()).hexdigest()[:24]

        with _lock:
            index = self._load_index()
            for row in index:
                if row.get("ingest_key") == ingest_key:
                    return DedupVerdict(True, "L1", ingest_key, 1.0, "exact_ingest_key")
                if url_key and row.get("url_key") == url_key:
                    return DedupVerdict(True, "L1", url_key, 1.0, "url_hash")
                if row.get("title_fp") == title_fp and row.get("body_hash") == body_hash:
                    return DedupVerdict(True, "L1", title_fp, 1.0, "title_body_hash")

            norm = normalize_text_for_match(text or "")
            for row in index[-400:]:
                prior = row.get("text_norm") or ""
                if not prior or len(norm) < 40:
                    continue
                ratio = difflib.SequenceMatcher(None, norm[:2000], prior[:2000]).ratio()
                if ratio >= self._l2_threshold:
                    return DedupVerdict(
                        True,
                        "L2",
                        str(row.get("ingest_key") or ""),
                        ratio,
                        "lexical_similarity",
                    )

        return DedupVerdict(False, "none")

    def register(self, *, source: str, message_id: int, text: str, url: str = "") -> str:
        ingest_key = build_ingest_key(source, message_id, text)
        row = {
            "ts_unix": round(time.time(), 3),
            "ingest_key": ingest_key,
            "source": (source or "")[:120],
            "message_id": int(message_id),
            "title_fp": _title_fingerprint(text),
            "body_hash": _content_hash(text),
            "text_norm": normalize_text_for_match(text or "")[:4000],
            "url_key": hashlib.sha256(url.strip().lower().encode()).hexdigest()[:24] if url.strip() else "",
        }
        path = dedup_index_path(self._runtime_dir)
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            _trim_index(path)
        return ingest_key

    def _load_index(self) -> list[dict[str, Any]]:
        path = dedup_index_path(self._runtime_dir)
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except OSError:
            pass
        return rows[-_MAX_INDEX_LINES:]


def _trim_index(path: Any) -> None:
    try:
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) <= _MAX_INDEX_LINES:
            return
        path.write_text("".join(lines[-_MAX_INDEX_LINES:]), encoding="utf-8")
    except OSError:
        pass
