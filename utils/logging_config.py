from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO", *, soak_test: bool = False) -> None:
    """
    Root logging setup. Use utils.structured_log.log_event for machine-friendly
    key=value JSON suffixes on important operational messages.

    Production-lite: keep LOG_LEVEL at INFO (avoid DEBUG in long-running soak tests —
    DEBUG from Telethon/HTTP floods disks). Log volume is also capped per field via
    LOG_MAX_FIELD_LEN (see structured_log). Prefer Docker log rotation / max-size
    (e.g. compose logging driver options) or systemd journal limits for unbounded growth.
    """
    root = logging.getLogger()
    if root.handlers:
        for h in list(root.handlers):
            root.removeHandler(h)

    log_level = getattr(logging, level.upper(), logging.INFO)
    if soak_test and log_level > logging.INFO:
        log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
