from __future__ import annotations

import hashlib
import re


def normalize_text_for_match(text: str) -> str:
    t = text.strip().lower()
    return re.sub(r"\s+", " ", t)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(normalize_text_for_match(text).encode("utf-8")).hexdigest()
