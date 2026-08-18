from __future__ import annotations

from typing import Any


def _call(obj: Any, name: str, default: str = "") -> str:
    method = getattr(obj, name, None)
    if not callable(method):
        return default
    try:
        value = method()
    except Exception:
        return default
    return "" if value is None else str(value)


def platform_id(event: Any) -> str:
    return _call(event, "get_platform_id") or _call(event, "get_platform_name") or "aiocqhttp"


def platform_name(event: Any) -> str:
    return _call(event, "get_platform_name") or "aiocqhttp"


def group_id(event: Any) -> str:
    value = _call(event, "get_group_id")
    if value:
        return value
    message_obj = getattr(event, "message_obj", None)
    return str(getattr(message_obj, "group_id", "") or "")


def sender_id(event: Any) -> str:
    return _call(event, "get_sender_id")


def is_group_message(event: Any) -> bool:
    return bool(group_id(event))


def session_key(event: Any) -> str:
    gid = group_id(event)
    pid = platform_id(event)
    if gid:
        return f"{pid}:GroupMessage:{gid}"
    umo = getattr(event, "unified_msg_origin", "") or ""
    return str(umo)


def session_umo(event: Any) -> str:
    return session_key(event)
