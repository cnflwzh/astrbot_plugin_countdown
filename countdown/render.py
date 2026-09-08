from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from string import Formatter

from .models import Task

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
WEEKDAYS_SHORT = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


MAX_TEMPLATE_OUTPUT = 4096
_FORMATTER = Formatter()
_FORMAT_NUMBERS = re.compile(r"\d+")


def _format_bounded(template: str, ctx: dict[str, object], depth: int = 2) -> str:
    if depth < 0 or len(template) > MAX_TEMPLATE_OUTPUT:
        raise ValueError("template is too large or nested too deeply")
    parts: list[str] = []
    length = 0
    for literal, field, spec, conversion in _FORMATTER.parse(template):
        length += len(literal)
        parts.append(literal)
        if field is not None:
            # Never let a user template traverse attributes or index into values.
            if not field.isidentifier():
                raise ValueError("only named placeholders are supported")
            value = ctx.get(field, "{" + field + "}")
            if type(value) not in (str, int, float, bool):
                raise ValueError("unsupported placeholder value")
            if isinstance(value, str) and len(value) > MAX_TEMPLATE_OUTPUT:
                raise ValueError("placeholder value is too large")
            if conversion:
                value = _FORMATTER.convert_field(value, conversion)
            spec = _format_bounded(spec, ctx, depth - 1)
            # Check BEFORE format() can allocate padding or floating point precision.
            if any(int(number) > MAX_TEMPLATE_OUTPUT for number in _FORMAT_NUMBERS.findall(spec)):
                raise ValueError("format width or precision is too large")
            rendered = format(value, spec)
            length += len(rendered)
            parts.append(rendered)
        if length > MAX_TEMPLATE_OUTPUT:
            raise ValueError("rendered template is too large")
    return "".join(parts)


def header_context(now: datetime) -> dict[str, object]:
    weekday = now.weekday()
    return {
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "month_02": f"{now.month:02d}",
        "day_02": f"{now.day:02d}",
        "hour": now.hour,
        "minute": now.minute,
        "hour_02": f"{now.hour:02d}",
        "minute_02": f"{now.minute:02d}",
        "weekday": WEEKDAYS[weekday],
        "weekday_short": WEEKDAYS_SHORT[weekday],
        "today": f"{now.year}年{now.month}月{now.day}日",
        "today_iso": now.date().isoformat(),
    }


def task_delta_days(task: Task, now: datetime) -> int:
    if task.mode == "countdown":
        return (task.target_date() - now.date()).days
    return (now.date() - task.target_date()).days


def is_due(task: Task, now: datetime) -> bool:
    if task.mode != "countdown":
        return False
    if task.has_time:
        return now >= task.target_datetime()
    return task_delta_days(task, now) <= 0


def format_remain(days: int, hours: int, minutes: int) -> str:
    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes or not parts:
        parts.append(f"{minutes}分钟")
    return "".join(parts)


def remain_parts(task: Task, now: datetime) -> tuple[int, int, int, int]:
    target = task.target_datetime()
    if task.mode == "countdown":
        if task.has_time:
            total = int((target - now).total_seconds())
        else:
            total = task_delta_days(task, now) * 86400
    else:
        total = (
            int((now - target).total_seconds())
            if task.has_time
            else task_delta_days(task, now) * 86400
        )
    raw = total
    total = max(0, total)
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    return days, hours, minutes, raw


def task_context(
    task: Task, now: datetime, header: dict[str, object] | None = None
) -> dict[str, object]:
    ctx = dict(header or header_context(now))
    target = task.target_datetime()
    days, hours, minutes, raw = remain_parts(task, now)
    calendar_days = task_delta_days(task, now)
    target_text = f"{target.year}年{target.month}月{target.day}日"
    if task.has_time:
        target_text += f" {target.strftime('%H:%M')}"
    ctx.update(
        {
            "name": task.name,
            "mode": "倒计时" if task.mode == "countdown" else "正计时",
            "days": days,
            "days_raw": calendar_days,
            "hours": hours,
            "hours_raw": max(0, raw) // 3600,
            "minutes": minutes,
            "remain": format_remain(days, hours, minutes),
            "target": target_text,
            "target_iso": task.target_date().isoformat(),
            "target_year": target.year,
            "target_month": target.month,
            "target_day": target.day,
            "target_month_02": f"{target.month:02d}",
            "target_day_02": f"{target.day:02d}",
            "target_time": target.strftime("%H:%M") if task.has_time else "",
        }
    )
    return ctx


def render_template(template: str, ctx: dict[str, object]) -> str:
    raw = template or ""
    if len(raw) > MAX_TEMPLATE_OUTPUT:
        return raw[:MAX_TEMPLATE_OUTPUT]
    try:
        return _format_bounded(raw, ctx)
    except (ValueError, TypeError, OverflowError):
        return raw


@dataclass
class RenderedItem:
    name: str
    text: str
    days: int
    mode: str
    is_today: bool
    has_time: bool
    target_time: str
    remain: str = ""
    is_due: bool = False
    index: int = 0


def resolve_item_template(
    task: Task,
    now: datetime,
    *,
    today_template: str,
    countdown_template: str,
    countdown_time_template: str,
    countup_template: str,
) -> str:
    if is_due(task, now):
        return today_template or "{name}就在今天！"
    if task.template.strip():
        return task.template
    if task.mode == "countup":
        return countup_template
    if task.has_time:
        return countdown_time_template or "距离{name}还有{remain}"
    return countdown_template


def build_render_items(
    tasks: list[Task],
    now: datetime,
    *,
    header_template: str,
    countdown_template: str,
    countup_template: str,
    today_template: str,
    countdown_time_template: str = "距离{name}还有{remain}",
    item_prefix: str = "- ",
    source_tasks: list[Task] | None = None,
) -> tuple[str, str, list[RenderedItem]]:
    header_ctx = header_context(now)
    header = render_template(header_template, header_ctx).rstrip()
    index_map = {task.id: index for index, task in enumerate(source_tasks or tasks, start=1)}
    ordered = sorted(
        tasks,
        key=lambda task: (
            0 if task.mode == "countdown" else 1,
            task_delta_days(task, now) if task.mode == "countdown" else -task_delta_days(task, now),
            task.name,
        ),
    )
    items: list[RenderedItem] = []
    lines: list[str] = []
    if header:
        lines.append(header)
    for task in ordered:
        days = task_delta_days(task, now)
        is_today = task.mode == "countdown" and days <= 0
        template = resolve_item_template(
            task,
            now,
            today_template=today_template,
            countdown_template=countdown_template,
            countdown_time_template=countdown_time_template,
            countup_template=countup_template,
        )
        ctx = task_context(task, now, header_ctx)
        text = render_template(template, ctx)
        items.append(
            RenderedItem(
                name=task.name,
                text=text,
                days=days,
                mode=task.mode,
                is_today=is_today,
                has_time=task.has_time,
                target_time=task.target_datetime().strftime("%H:%M") if task.has_time else "",
                remain=str(ctx.get("remain") or ""),
                is_due=is_due(task, now),
                index=index_map.get(task.id, 0),
            )
        )
        lines.append(f"{item_prefix}{text}")
    return header, "\n".join(lines), items


def render_broadcast(
    tasks: list[Task],
    now: datetime,
    *,
    header_template: str,
    countdown_template: str,
    countup_template: str,
    today_template: str = "{name}就在今天！",
    countdown_time_template: str = "距离{name}还有{remain}",
    item_prefix: str = "- ",
) -> str:
    _, text, _ = build_render_items(
        tasks,
        now,
        header_template=header_template,
        countdown_template=countdown_template,
        countup_template=countup_template,
        today_template=today_template,
        countdown_time_template=countdown_time_template,
        item_prefix=item_prefix,
    )
    return text


def preserve_newlines(text: str) -> str:
    """aiocqhttp strips surrounding whitespace; wrap with ZWSP to keep newlines."""
    return f"\u200b{text}\u200b"
