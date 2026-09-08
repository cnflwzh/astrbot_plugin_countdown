from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .logic import find_task, name_exists
from .models import SessionState, Task, TaskMode
from .parse import ParsedDate, ParseError, parse_bool, parse_datetime
from .store import JsonStore


def _validate_name(session: SessionState, name: str, *, exclude_id: str | None = None) -> None:
    if not name:
        raise ParseError("名称不能为空。")
    if len(name) > 50:
        raise ParseError("名称过长，最多 50 个字符。")
    if name_exists(session, name, exclude_id=exclude_id):
        raise ParseError(f"本群已存在同名任务「{name}」。")


def _validate_template(template: str) -> None:
    if len(template) > 200:
        raise ParseError("模板过长，最多 200 个字符。")


def _validate_date(parsed: ParsedDate, mode: TaskMode, now: datetime) -> None:
    days = (parsed.value.date() - now.date()).days
    if mode == "countdown":
        if parsed.has_time and parsed.value <= now:
            raise ParseError("倒计时的目标时间不能早于现在。")
        if not parsed.has_time and days < 0:
            raise ParseError("倒计时的目标日期不能早于今天。")
    if mode == "countup" and days > 0:
        raise ParseError("正计时的起始日期不能晚于今天。")


def create_task(
    store: JsonStore,
    session: SessionState,
    *,
    name: str,
    parsed_date: ParsedDate,
    template: str,
    mode: TaskMode,
    now: datetime,
    created_by: str,
    limit: int,
) -> Task:
    name = name.strip()
    _validate_name(session, name)
    _validate_template(template)
    _validate_date(parsed_date, mode, now)
    if len(session.tasks) >= limit:
        raise ParseError(f"本群任务数已达上限（{limit}）。")
    task = Task(
        id=str(session.next_seq),
        name=name,
        mode=mode,
        target=parsed_date.iso,
        template=template,
        created_by=created_by,
        created_at=now.isoformat(timespec="seconds"),
        has_time=parsed_date.has_time,
    )
    return store.add_task(session, task)


def edit_task(
    store: JsonStore,
    session: SessionState,
    *,
    target: str,
    field: str,
    value: str,
    now: datetime,
) -> Task:
    task = find_task(session, target)
    if task is None:
        raise ParseError("没有找到对应任务，先用 /倒计时 列表 查看序号。")
    updated = replace(task, revision=task.revision + 1)
    if field == "name":
        updated.name = value.strip()
        _validate_name(session, updated.name, exclude_id=task.id)
    elif field == "template":
        _validate_template(value)
        updated.template = value
    elif field == "enabled":
        updated.enabled = parse_bool(value)
    elif field == "date":
        parsed, extra = parse_datetime(
            value.split(), now.date(), future_md=task.mode == "countdown"
        )
        if extra:
            raise ParseError("日期格式不正确。")
        _validate_date(parsed, task.mode, now)
        updated.target = parsed.iso
        updated.has_time = parsed.has_time
        updated.pre_reminded = False
        updated.due_reminded = False
    else:
        raise ParseError("可修改字段：名称、日期、模板、开关。")
    store.mutate(lambda: vars(task).update(vars(updated)))
    return task
