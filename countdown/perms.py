from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _as_id_set(values: Iterable[Any]) -> set[str]:
    result: set[str] = set()
    for item in values or []:
        text = str(item).strip()
        if text:
            result.add(text)
    return result


def sender_id(event: Any) -> str:
    getter = getattr(event, "get_sender_id", None)
    if callable(getter):
        try:
            return str(getter() or "")
        except Exception:
            return ""
    return ""


def is_astrbot_admin(event: Any, context: Any | None = None) -> bool:
    checker = getattr(event, "is_admin", None)
    if callable(checker):
        try:
            if checker():
                return True
        except Exception:
            pass
    if getattr(event, "role", "") == "admin":
        return True
    if context is None:
        return False
    try:
        config = context.get_config()
        admins = config.get("admins_id", []) if config is not None else []
    except Exception:
        admins = []
    return sender_id(event) in _as_id_set(admins)


def qq_group_role(event: Any) -> str:
    message_obj = getattr(event, "message_obj", None)
    sender = getattr(message_obj, "sender", None)
    role = getattr(sender, "role", None)
    if role:
        return str(role)
    raw = getattr(message_obj, "raw_message", None)
    if isinstance(raw, dict):
        return str((raw.get("sender") or {}).get("role") or "")
    return ""


def is_qq_group_admin(event: Any) -> bool:
    return qq_group_role(event) in {"owner", "admin"}


def can_manage(
    event: Any,
    *,
    context: Any | None,
    mode: str,
    plugin_admin_ids: Iterable[Any],
) -> bool:
    if is_astrbot_admin(event, context):
        return True
    normalized = (mode or "astrbot_admin").strip().lower()
    if normalized == "all":
        return True
    uid = sender_id(event)
    if normalized == "plugin_admin":
        return uid in _as_id_set(plugin_admin_ids)
    if normalized == "group_admin":
        return is_qq_group_admin(event)
    return False


def can_query(
    event: Any,
    *,
    context: Any | None,
    allow_all: bool,
    mode: str,
    plugin_admin_ids: Iterable[Any],
) -> bool:
    if allow_all:
        return True
    return can_manage(event, context=context, mode=mode, plugin_admin_ids=plugin_admin_ids)
