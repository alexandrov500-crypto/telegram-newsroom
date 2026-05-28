"""Forensic guards on aiogram Bot media sends — catch legacy kwargs at runtime."""

from __future__ import annotations

import hashlib
import logging
import os
import traceback
from typing import Any, Callable

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

FORBIDDEN_MEDIA_KWARGS = frozenset(
    {
        "disable_web_page_preview",
        "link_preview_options",
    }
)

_MEDIA_METHODS = (
    "send_photo",
    "send_video",
    "send_document",
    "send_animation",
    "send_media_group",
)

_PATCHED = False


def forensic_media_enabled() -> bool:
    raw = os.getenv("TELEGRAM_MEDIA_FORENSIC", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def assert_media_kwargs_fail_closed(
    kwargs: dict[str, Any],
    *,
    transport_method: str,
    caller_module: str,
    draft_id: int | None = None,
) -> None:
    illegal = FORBIDDEN_MEDIA_KWARGS.intersection(kwargs.keys())
    if not illegal:
        return
    stack = traceback.format_stack(limit=24)
    log_event(
        logger,
        "FORBIDDEN_MEDIA_KWARGS_DETECTED",
        illegal=sorted(illegal),
        kwargs_keys=sorted(kwargs.keys()),
        transport_method=transport_method,
        caller_module=caller_module,
        draft_id=draft_id,
        stack=stack,
    )
    logger.critical(
        "FORBIDDEN_MEDIA_KWARGS_DETECTED method=%s illegal=%s caller=%s",
        transport_method,
        sorted(illegal),
        caller_module,
    )
    raise RuntimeError(
        f"Forbidden media kwargs {sorted(illegal)} for {transport_method} "
        f"(caller={caller_module}); see FORENSIC_MEDIA_SEND / stack in logs"
    )


def _log_forensic_media_send(
    *,
    transport_method: str,
    kwargs: dict[str, Any],
    caller_module: str,
    draft_id: int | None = None,
) -> None:
    if not forensic_media_enabled():
        return
    stack = traceback.format_stack(limit=28)
    log_event(
        logger,
        "FORENSIC_MEDIA_SEND",
        transport_method=transport_method,
        module=caller_module,
        kwargs_keys=sorted(kwargs.keys()),
        draft_id=draft_id,
        stack=stack,
    )
    logger.critical(
        "FORENSIC_MEDIA_SEND method=%s module=%s keys=%s",
        transport_method,
        caller_module,
        sorted(kwargs.keys()),
    )


def install_media_send_forensic_guards() -> None:
    """Patch Bot media methods once per process — logs stack + fail-closed on forbidden kwargs."""
    global _PATCHED
    if _PATCHED:
        return
    from aiogram import Bot

    for method_name in _MEDIA_METHODS:
        original = getattr(Bot, method_name, None)
        if original is None or getattr(original, "_newsroom_forensic_wrapped", False):
            continue

        def _make_wrapper(name: str, orig: Callable[..., Any]) -> Callable[..., Any]:
            async def wrapped(self: Bot, *args: Any, **kwargs: Any) -> Any:
                caller = __file__
                _log_forensic_media_send(
                    transport_method=name,
                    kwargs=kwargs,
                    caller_module=caller,
                )
                assert_media_kwargs_fail_closed(
                    kwargs,
                    transport_method=name,
                    caller_module=caller,
                )
                return await orig(self, *args, **kwargs)

            wrapped._newsroom_forensic_wrapped = True  # type: ignore[attr-defined]
            return wrapped

        setattr(Bot, method_name, _make_wrapper(method_name, original))

    _PATCHED = True
    log_event(logger, "telegram_forensic.installed", methods=list(_MEDIA_METHODS))


def bot_token_fingerprint(token: str) -> str:
    t = (token or "").strip()
    if len(t) < 12:
        return "invalid"
    digest = hashlib.sha256(t.encode("utf-8")).hexdigest()[:12]
    return f"{t[:4]}…{t[-4:]}:{digest}"


def log_runtime_code_identity(*, bot_token: str = "") -> None:
    import publisher.telegram_transport as tt
    from app.build_provenance import load_build_provenance
    from app.ops.runtime.active_runtime import load_active_runtime
    from app.ops.runtime.singleton_guard import get_singleton_guard

    prov = load_build_provenance()
    rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    sg = get_singleton_guard(rd)
    payload = {
        "pid": os.getpid(),
        "git_sha": prov.git_sha,
        "build_version": prov.build_version,
        "telegram_transport_file": getattr(tt, "__file__", ""),
        "cwd": os.getcwd(),
        "bot_token_fingerprint": bot_token_fingerprint(bot_token),
        "singleton_lock_owner": sg.is_owner(),
        "singleton_lock_path": str(sg.path),
        "active_runtime": load_active_runtime(rd),
        "forensic_media_enabled": forensic_media_enabled(),
    }
    log_event(logger, "RUNTIME_CODE_IDENTITY", **payload)
    logger.critical("RUNTIME_CODE_IDENTITY %s", payload)
