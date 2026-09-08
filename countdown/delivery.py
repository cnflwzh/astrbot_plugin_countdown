from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from typing import Literal

from .logic import due_for_cleanup
from .models import SessionState, Task
from .store import JsonStore

logger = logging.getLogger(__name__)


async def send_reminders(
    store: JsonStore,
    session: SessionState,
    *,
    flag: Literal["pre_reminded", "due_reminded"],
    is_pending: Callable[[Task], bool],
    send: Callable[[Task], Awaitable[bool | None]],
) -> None:
    for task in list(session.tasks):
        if not any(current is task for current in session.tasks) or not is_pending(task):
            continue
        snapshot = replace(task)
        try:
            result = await send(snapshot)
        except Exception:
            logger.exception("failed to send %s for task %s in %s", flag, task.id, session.key)
            continue
        if result is False:
            logger.warning("%s send returned False for %s", flag, session.key)
            continue
        if task != snapshot or not any(current is task for current in session.tasks):
            continue
        # Persist each successful delivery before awaiting another send. An edit
        # increments revision, so an old delivery cannot acknowledge a new task.
        store.mutate(lambda: setattr(task, flag, True))


def finish_broadcast(
    store: JsonStore,
    session: SessionState,
    sent_tasks: list[Task],
    now: datetime,
    *,
    cleanup: bool,
) -> None:
    sent_by_id = {task.id: task for task in sent_tasks}

    def apply():
        session.last_broadcast_date = now.date().isoformat()
        if cleanup:
            session.tasks = [
                task
                for task in session.tasks
                if task != sent_by_id.get(task.id)
                or not due_for_cleanup(task, now, include_date_only_zero=True)
            ]

    store.mutate(apply)
