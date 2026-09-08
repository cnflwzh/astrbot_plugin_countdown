import asyncio
from dataclasses import replace
from datetime import datetime

import pytest

from countdown.delivery import finish_broadcast, send_reminders
from countdown.logic import should_due_remind
from countdown.models import Task
from countdown.store import JsonStore


def _state(tmp_path):
    store = JsonStore(tmp_path / "data.json")
    session = store.ensure_session(
        "qq:GroupMessage:1", umo="qq:GroupMessage:1", platform_id="qq", group_id="1", is_group=True
    )
    task = Task(
        "1", "发布", "countdown", "2060-01-01T18:00:00", "", "1", "2026-01-01", has_time=True
    )
    store.add_task(session, task)
    return store, session, task


@pytest.mark.parametrize("flag", ["pre_reminded", "due_reminded"])
def test_edit_during_send_cannot_mark_new_task(tmp_path, flag):
    store, session, task = _state(tmp_path)

    async def send(snapshot):
        assert snapshot.target == "2060-01-01T18:00:00"
        task.target = "2060-01-02T18:00:00"
        task.revision += 1
        return True

    asyncio.run(send_reminders(store, session, flag=flag, is_pending=lambda _: True, send=send))
    assert not getattr(task, flag)


def test_deleted_pending_task_is_not_sent(tmp_path):
    store, session, task = _state(tmp_path)
    second = replace(task, id="2")
    store.add_task(session, second)
    sent = []

    async def send(snapshot):
        sent.append(snapshot.id)
        store.remove_task(session, second)
        return True

    asyncio.run(
        send_reminders(store, session, flag="due_reminded", is_pending=lambda _: True, send=send)
    )
    assert sent == ["1"]


@pytest.mark.parametrize("failure", [False, OSError("send failed")])
def test_failed_reminder_is_retried_and_success_is_persisted(tmp_path, failure):
    store, session, task = _state(tmp_path)

    async def send_fail(snapshot):
        if isinstance(failure, Exception):
            raise failure
        return failure

    async def send_ok(snapshot):
        return True

    def pending(task):
        return should_due_remind(task, datetime(2060, 1, 2))

    asyncio.run(
        send_reminders(store, session, flag="due_reminded", is_pending=pending, send=send_fail)
    )
    assert not task.due_reminded
    asyncio.run(
        send_reminders(store, session, flag="due_reminded", is_pending=pending, send=send_ok)
    )
    store.load()
    assert store.get_session(session.key).tasks[0].due_reminded


def test_success_survives_cancellation_of_later_send(tmp_path):
    store, session, task = _state(tmp_path)
    store.add_task(session, replace(task, id="2"))

    async def send(snapshot):
        if snapshot.id == "2":
            raise asyncio.CancelledError
        return True

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            send_reminders(
                store, session, flag="due_reminded", is_pending=lambda _: True, send=send
            )
        )
    store.load()
    tasks = store.get_session(session.key).tasks
    assert tasks[0].due_reminded
    assert not tasks[1].due_reminded


def test_daily_cleanup_only_removes_unchanged_sent_tasks(tmp_path):
    store, session, task = _state(tmp_path)
    task.target = "2060-01-01"
    task.has_time = False
    other = replace(task, id="2", name="已发送")
    session.tasks.append(other)
    snapshots = [replace(item) for item in session.tasks]
    task.revision += 1
    added = replace(task, id="3", name="刚添加")
    session.tasks.append(added)
    finish_broadcast(store, session, snapshots, datetime(2060, 1, 1, 9), cleanup=True)
    assert session.tasks == [task, added]
    assert session.last_broadcast_date == "2060-01-01"


def test_same_date_edit_during_send_keeps_new_reminder_pending(tmp_path):
    from countdown.operations import edit_task

    store, session, task = _state(tmp_path)

    async def send(snapshot):
        edit_task(
            store,
            session,
            target="1",
            field="date",
            value="2060-01-01 18:00",
            now=datetime(2060, 1, 1, 17, 59),
        )
        return True

    asyncio.run(
        send_reminders(store, session, flag="pre_reminded", is_pending=lambda _: True, send=send)
    )
    assert not task.pre_reminded
    assert task.revision == 1


def test_cleanup_disabled_keeps_sent_date_only_task(tmp_path):
    store, session, task = _state(tmp_path)
    task.target = "2060-01-01"
    task.has_time = False
    finish_broadcast(store, session, [replace(task)], datetime(2060, 1, 1, 9), cleanup=False)
    assert session.tasks == [task]
