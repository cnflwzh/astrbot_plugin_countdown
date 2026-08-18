from datetime import datetime

from countdown.logic import (
    expired_countdowns,
    find_task,
    should_broadcast,
    should_due_remind,
    should_pre_remind,
    tasks_for_broadcast,
)
from countdown.models import SessionState, Task


def _session(*tasks: Task, **kwargs) -> SessionState:
    payload = {
        "key": "aiocqhttp:GroupMessage:123",
        "umo": "aiocqhttp:GroupMessage:123",
        "platform_id": "aiocqhttp",
        "group_id": "123",
        "tasks": list(tasks),
    }
    payload.update(kwargs)
    return SessionState(**payload)


def _task(
    task_id: str,
    name: str,
    mode: str,
    target: str,
    enabled: bool = True,
    has_time: bool = False,
    pre_reminded: bool = False,
) -> Task:
    return Task(
        id=task_id,
        name=name,
        mode=mode,  # type: ignore[arg-type]
        target=target,
        template="",
        created_by="1",
        created_at="2026-01-01T00:00:00",
        enabled=enabled,
        has_time=has_time,
        pre_reminded=pre_reminded,
    )


def test_should_broadcast_window():
    session = _session(_task("1", "Dota3", "countdown", "2060-01-31"), broadcast_time="09:00")
    now = datetime(2026, 8, 18, 9, 5, 0)
    assert should_broadcast(session, now, default_time="09:00", catch_up_minutes=10) is True
    assert should_broadcast(session, now, default_time="09:00", catch_up_minutes=3) is False

    session.last_broadcast_date = "2026-08-18"
    assert should_broadcast(session, now, default_time="09:00", catch_up_minutes=10) is False


def test_should_not_broadcast_before_time_or_when_disabled():
    session = _session(_task("1", "Dota3", "countdown", "2060-01-31"), broadcast_time="09:00")
    early = datetime(2026, 8, 18, 8, 59, 0)
    assert should_broadcast(session, early, default_time="09:00", catch_up_minutes=10) is False

    session.broadcast_enabled = False
    now = datetime(2026, 8, 18, 9, 0, 0)
    assert should_broadcast(session, now, default_time="09:00", catch_up_minutes=10) is False


def test_expired_and_zero_day_cleanup():
    now = datetime(2060, 1, 1, 9, 0, 0)
    zero = _task("1", "前瞻", "countdown", "2060-01-01")
    future = _task("2", "Dota3", "countdown", "2060-01-31")
    overdue = _task("3", "旧活动", "countdown", "2059-12-01")
    countup = _task("4", "开服", "countup", "2024-01-01")
    session = _session(zero, future, overdue, countup)

    broadcastable = {task.name for task in tasks_for_broadcast(session, now)}
    assert broadcastable == {"前瞻", "Dota3", "开服"}

    overdue_only = expired_countdowns(session, now, cleanup_after_zero=True, include_zero=False)
    assert [task.name for task in overdue_only] == ["旧活动"]

    after_broadcast = expired_countdowns(session, now, cleanup_after_zero=True, include_zero=True)
    assert {task.name for task in after_broadcast} == {"前瞻", "旧活动"}


def test_find_task_by_index_and_name():
    session = _session(
        _task("10", "《Dota3》", "countdown", "2060-01-31"),
        _task("11", "开服", "countup", "2024-01-01"),
    )
    assert find_task(session, "1").name == "《Dota3》"
    assert find_task(session, "开服").name == "开服"
    assert find_task(session, "Dota3").name == "《Dota3》"
    assert find_task(session, "10").name == "《Dota3》"
    assert find_task(session, "不存在") is None


def test_timed_task_not_cleaned_before_clock():
    now = datetime(2060, 1, 1, 9, 0, 0)
    timed = _task("1", "Dota3", "countdown", "2060-01-01T18:00:00", has_time=True)
    date_only = _task("2", "前瞻", "countdown", "2060-01-01")
    session = _session(timed, date_only)

    after_morning = expired_countdowns(session, now, cleanup_after_zero=True, include_zero=True)
    assert [task.name for task in after_morning] == ["前瞻"]

    after_release = expired_countdowns(
        session, datetime(2060, 1, 1, 18, 0, 0), cleanup_after_zero=True, include_zero=False
    )
    assert after_release == []

    timed.due_reminded = True
    after_due_remind = expired_countdowns(
        session, datetime(2060, 1, 1, 18, 0, 0), cleanup_after_zero=True, include_zero=False
    )
    assert [task.name for task in after_due_remind] == ["Dota3"]


def test_pre_remind_window():
    task = _task("1", "Dota3", "countdown", "2060-01-01T18:00:00", has_time=True)
    assert should_pre_remind(task, datetime(2060, 1, 1, 17, 50, 0), minutes=10) is True
    assert should_pre_remind(task, datetime(2060, 1, 1, 17, 55, 0), minutes=10) is True
    assert should_pre_remind(task, datetime(2060, 1, 1, 17, 40, 0), minutes=10) is False
    assert should_pre_remind(task, datetime(2060, 1, 1, 18, 0, 0), minutes=10) is False

    task.pre_reminded = True
    assert should_pre_remind(task, datetime(2060, 1, 1, 17, 50, 0), minutes=10) is False


def test_due_remind_at_target_time():
    task = _task("1", "Dota3", "countdown", "2060-01-01T18:00:00", has_time=True)
    assert should_due_remind(task, datetime(2060, 1, 1, 17, 59, 0)) is False
    assert should_due_remind(task, datetime(2060, 1, 1, 18, 0, 0)) is True
    assert should_due_remind(task, datetime(2060, 1, 1, 18, 5, 0)) is True
    task.due_reminded = True
    assert should_due_remind(task, datetime(2060, 1, 1, 18, 5, 0)) is False
