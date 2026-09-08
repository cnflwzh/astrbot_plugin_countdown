from __future__ import annotations

from datetime import datetime, timedelta

from .models import SessionState, Task
from .parse import format_clock, parse_clock
from .render import task_delta_days


def resolve_broadcast_clock(session: SessionState, default_time: str) -> tuple[int, int]:
    raw = session.broadcast_time or default_time or "09:00"
    return parse_clock(raw)


def should_broadcast(
    session: SessionState,
    now: datetime,
    *,
    default_time: str,
    catch_up_minutes: int,
) -> bool:
    if not session.broadcast_enabled:
        return False
    if not any(task.enabled for task in session.tasks):
        return False
    today = now.date().isoformat()
    if session.last_broadcast_date == today:
        return False
    hour, minute = resolve_broadcast_clock(session, default_time)
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta_minutes = (now - scheduled).total_seconds() // 60
    window = max(0, int(catch_up_minutes))
    return 0 <= delta_minutes <= window


def tasks_for_broadcast(session: SessionState, now: datetime) -> list[Task]:
    result: list[Task] = []
    for task in session.enabled_tasks():
        days = task_delta_days(task, now)
        if task.mode == "countdown" and days < 0:
            continue
        result.append(task)
    return result


def due_for_cleanup(task: Task, now: datetime, *, include_date_only_zero: bool) -> bool:
    if task.mode != "countdown" or not task.enabled:
        return False
    if task.has_time:
        return task.due_reminded and now >= task.target_datetime()
    days = task_delta_days(task, now)
    if days < 0:
        return True
    if days > 0:
        return False
    return include_date_only_zero


def expired_countdowns(
    session: SessionState,
    now: datetime,
    *,
    cleanup_after_zero: bool,
    include_zero: bool,
) -> list[Task]:
    if not cleanup_after_zero:
        return []
    return [
        task
        for task in session.tasks
        if due_for_cleanup(task, now, include_date_only_zero=include_zero)
    ]


def should_pre_remind(task: Task, now: datetime, *, minutes: int) -> bool:
    if not task.enabled or task.mode != "countdown" or not task.has_time:
        return False
    if task.pre_reminded or minutes <= 0:
        return False
    seconds = (task.target_datetime() - now).total_seconds()
    return 0 < seconds <= minutes * 60


def should_due_remind(task: Task, now: datetime) -> bool:
    if not task.enabled or task.mode != "countdown" or not task.has_time:
        return False
    if task.due_reminded:
        return False
    return now >= task.target_datetime()


def find_task(session: SessionState, token: str) -> Task | None:
    raw = (token or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        index = int(raw)
        if 1 <= index <= len(session.tasks):
            return session.tasks[index - 1]
        for task in session.tasks:
            if task.id == raw:
                return task
        return None
    stripped = raw.strip("《》")
    for task in session.tasks:
        if task.name == raw or task.name.strip("《》") == stripped:
            return task
    return None


def name_exists(session: SessionState, name: str, *, exclude_id: str | None = None) -> bool:
    target = name.strip()
    for task in session.tasks:
        if exclude_id and task.id == exclude_id:
            continue
        if task.name == target:
            return True
    return False


def minutes_until(now: datetime, hour: int, minute: int) -> int:
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= now:
        scheduled += timedelta(days=1)
    return int((scheduled - now).total_seconds() // 60)


def clock_label(session: SessionState, default_time: str) -> str:
    if session.broadcast_time:
        return session.broadcast_time
    try:
        hour, minute = parse_clock(default_time)
        return format_clock(hour, minute)
    except Exception:
        return "09:00"
