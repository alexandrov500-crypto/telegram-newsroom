from __future__ import annotations

from typing import Any

from bot.platform.context_holder import get_platform


async def invoke_internal(
    endpoint: str,
    *,
    client_id: str = "internal",
    scope: str = "read",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """SDK helper for internal gateway calls."""
    plat = get_platform()
    if plat is None:
        return {"ok": False, "error": "platform_offline"}
    return await plat.gateway.invoke(
        endpoint,
        client_id=client_id,
        scope=scope,
        payload=payload,
    )


def policy_simulate(kind: str, context: dict[str, Any]) -> dict[str, Any]:
    plat = get_platform()
    if plat is None:
        return {"allowed": False, "error": "platform_offline"}
    return plat.policies.simulate(kind, context)
