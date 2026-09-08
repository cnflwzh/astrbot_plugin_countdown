from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from .models import SessionState, StoreData, Task


class StoreError(RuntimeError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.data = StoreData()
        self._load_error: StoreError | None = None

    def load(self) -> None:
        with self._lock:
            try:
                try:
                    content = self.path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    if self._load_error is not None:
                        raise self._load_error
                    content = '{"sessions": {}}'
                loaded = StoreData.from_dict(json.loads(content, object_pairs_hook=_unique_object))
            except (
                OSError,
                ValueError,
                TypeError,
                AttributeError,
                RecursionError,
                StoreError,
            ) as exc:
                self._load_error = StoreError(
                    f"无法读取倒计时数据 {self.path}；已停止写入以保护原文件，请检查或恢复备份。"
                )
                raise self._load_error from exc
            self.data = loaded
            self._load_error = None

    def save(self) -> None:
        with self._lock:
            if self._load_error is not None:
                raise self._load_error
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.data.to_dict(), ensure_ascii=False, indent=2)
            tmp: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f"{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    tmp = Path(handle.name)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                tmp.replace(self.path)
            finally:
                if tmp is not None:
                    tmp.unlink(missing_ok=True)

    def get_session(self, key: str) -> SessionState | None:
        with self._lock:
            return self.data.sessions.get(key)

    def ensure_session(
        self,
        key: str,
        *,
        umo: str,
        platform_id: str,
        group_id: str,
        is_group: bool,
    ) -> SessionState:
        with self._lock:
            if not key or not umo or not platform_id:
                raise ValueError("session identity must not be empty")
            session = self.data.sessions.get(key)
            if session is None:
                session = SessionState(
                    key=key,
                    umo=umo,
                    platform_id=platform_id,
                    group_id=group_id,
                    is_group=is_group,
                )
                self.data.sessions[key] = session
            else:
                session.umo = umo or session.umo
                session.platform_id = platform_id or session.platform_id
                session.group_id = group_id or session.group_id
                session.is_group = is_group
            return session

    def iter_sessions(self) -> list[SessionState]:
        with self._lock:
            return list(self.data.sessions.values())

    def add_task(self, session: SessionState, task: Task) -> Task:
        def apply():
            if any(item.id == task.id for item in session.tasks):
                raise ValueError("duplicate task id")
            session.tasks.append(task)
            try:
                session.next_seq = max(session.next_seq, int(task.id) + 1)
            except ValueError:
                session.next_seq = max(session.next_seq, len(session.tasks) + 1)

        self.mutate(apply)
        return task

    def remove_task(self, session: SessionState, task: Task) -> None:
        def apply():
            session.tasks = [item for item in session.tasks if item.id != task.id]

        self.mutate(apply)

    def mutate(self, fn: Callable[[], None]) -> None:
        with self._lock:
            if self._load_error is not None:
                raise self._load_error
            version = self.data.version
            sessions = self.data.sessions.copy()
            snapshots = [
                (
                    session,
                    {**vars(session), "tasks": list(session.tasks)},
                    [(task, vars(task).copy()) for task in session.tasks],
                )
                for session in sessions.values()
            ]
            try:
                fn()
                self.save()
            except BaseException:
                # Restore existing references as async senders may still hold them.
                self.data.version = version
                self.data.sessions = sessions
                for session, state, tasks in snapshots:
                    vars(session).update(state)
                    for task, task_state in tasks:
                        vars(task).update(task_state)
                raise

    def next_id(self, session: SessionState) -> str:
        with self._lock:
            value = str(session.next_seq)
            session.next_seq += 1
            return value
