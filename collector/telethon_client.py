from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.sessions import SQLiteSession, StringSession

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _build_proxy_kwargs() -> dict:
    """Parse TELETHON_PROXY into TelegramClient kwargs.

    Supported forms (use a trusted proxy only — the user session flows through it):
      socks5://[user:pass@]host:port
      socks4://host:port
      http://[user:pass@]host:port      (CONNECT proxy)
      mtproxy://host:port?secret=HEX    (or mtproxy://HEXSECRET@host:port)
    """
    raw = os.getenv("TELETHON_PROXY", "").strip()
    if not raw:
        return {}
    from urllib.parse import parse_qs, urlparse

    u = urlparse(raw)
    scheme = (u.scheme or "").lower()
    host, port = u.hostname, u.port
    if not host or not port:
        log_event(logger, "telethon.proxy_invalid", value=raw[:40])
        return {}

    if scheme == "mtproxy":
        secret = (u.username or parse_qs(u.query).get("secret", [""])[0] or "").strip()
        from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

        log_event(logger, "telethon.proxy", kind="mtproxy", host=host, port=port)
        return {
            "connection": ConnectionTcpMTProxyRandomizedIntermediate,
            "proxy": (host, port, secret),
        }

    if scheme in ("socks5", "socks4", "http"):
        proxy: dict[str, object] = {"proxy_type": scheme, "addr": host, "port": port, "rdns": True}
        if u.username:
            proxy["username"] = u.username
        if u.password:
            proxy["password"] = u.password
        log_event(logger, "telethon.proxy", kind=scheme, host=host, port=port)
        return {"proxy": proxy}

    log_event(logger, "telethon.proxy_unsupported", scheme=scheme)
    return {}


def build_telethon_client(
    *,
    api_id: int,
    api_hash: str,
    session_string: str | None = None,
    session_path: str | None = None,
) -> TelegramClient:
    if (session_string or "").strip():
        session = StringSession(session_string.strip())
        log_event(logger, "telethon.session_backend", backend="string")
    elif session_path:
        session = SQLiteSession(session_path)
        log_event(logger, "telethon.session_backend", backend="sqlite", path=session_path)
    else:
        session = StringSession("")
        log_event(logger, "telethon.session_backend", backend="string", empty=True)

    use_ipv6 = os.getenv("TELETHON_USE_IPV6", "false").strip().lower() in ("1", "true", "yes", "on")
    proxy_kwargs = _build_proxy_kwargs()
    log_event(logger, "telethon.transport", use_ipv6=use_ipv6, proxy=bool(proxy_kwargs.get("proxy")))
    return TelegramClient(session, api_id, api_hash, use_ipv6=use_ipv6, **proxy_kwargs)


def to_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
