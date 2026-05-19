from __future__ import annotations

import hashlib
import re
import string

_DEFAULT_THRESHOLD = 0.72

_PUNCT_TABLE = str.maketrans("", "", string.punctuation.replace("-", ""))
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]{1,}")

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "after",
        "before",
        "into",
        "over",
        "about",
        "says",
        "said",
        "new",
        "how",
        "why",
        "what",
        "when",
        "who",
    }
)

_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    ("ingly", ""),
    ("edly", ""),
    ("ness", ""),
    ("ment", ""),
    ("ions", ""),
    ("ing", ""),
    ("ers", "er"),
    ("ies", "y"),
    ("es", ""),
    ("ed", ""),
    ("ly", ""),
    ("s", ""),
)


def normalize_title(title: str) -> str:
    text = title.lower().strip()
    text = text.translate(_PUNCT_TABLE)
    text = re.sub(r"\s+", " ", text)
    return text


def simple_stem(token: str) -> str:
    if len(token) <= 3:
        return token
    for suffix, replacement in _SUFFIX_RULES:
        if token.endswith(suffix) and len(token) - len(suffix) + len(replacement) >= 3:
            return token[: -len(suffix)] + replacement
    return token


def tokenize_title(title: str) -> set[str]:
    normalized = normalize_title(title)
    tokens: set[str] = set()
    for raw in _TOKEN_RE.findall(normalized):
        stemmed = simple_stem(raw)
        if stemmed in _STOPWORDS or len(stemmed) < 2:
            continue
        tokens.add(stemmed)
    return tokens


def fingerprint_hash(tokens: set[str]) -> str:
    """Stable hash for logging / storage key."""
    payload = "|".join(sorted(tokens))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def tokens_to_storage(tokens: set[str]) -> str:
    return "|".join(sorted(tokens))


def storage_to_tokens(storage: str) -> set[str]:
    if not storage:
        return set()
    return {part for part in storage.split("|") if part}


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    if union == 0:
        return 0.0
    return intersection / union


def build_fingerprint(title: str) -> tuple[set[str], str]:
    tokens = tokenize_title(title)
    return tokens, fingerprint_hash(tokens)


def best_cluster_match(
    fingerprint: set[str],
    candidates: list[tuple[int, str]],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
) -> tuple[int, float] | None:
    """Return (cluster_id, score) for best match at or above threshold."""
    best_id: int | None = None
    best_score = 0.0
    for cluster_id, stored in candidates:
        score = jaccard_similarity(fingerprint, storage_to_tokens(stored))
        if score > best_score:
            best_score = score
            best_id = cluster_id
    if best_id is None or best_score < threshold:
        return None
    return best_id, best_score
