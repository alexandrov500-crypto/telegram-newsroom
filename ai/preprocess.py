from __future__ import annotations

import logging

from db.models import RawPost
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def truncate_raw_posts_for_openai(
    posts: list[RawPost],
    *,
    max_chars_per_post: int,
    log: logging.Logger | None = None,
) -> tuple[list[RawPost], int]:
    """
    Truncate in-memory post text (no DB flush). Returns posts and total char count.
    """
    lg = log or logger
    total = 0
    truncated_count = 0
    for p in posts:
        t = p.text or ""
        if len(t) > max_chars_per_post:
            p.text = t[: max_chars_per_post - 1].rstrip() + "…"
            truncated_count += 1
        total += len(p.text)
    if truncated_count:
        log_event(lg, "openai.preprocess_truncated_posts", count=truncated_count, max_chars=max_chars_per_post)
    heavy_threshold = max_chars_per_post * max(1, len(posts)) * 3 // 4
    if total > heavy_threshold:
        log_event(lg, "openai.preprocess_token_heavy_hint", total_chars=total, posts=len(posts))
    return posts, total
