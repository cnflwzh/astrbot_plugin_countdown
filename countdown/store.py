from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path

from .models import SessionState, StoreData, Task


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.data = StoreData()

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.data = StoreData()
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.data = StoreData.from_dict(raw if isinstance(raw, dict) else {})
            except Exception:
                self.data = StoreData()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.data.to_dict(), ensure_ascii=False, indent=2)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self.path)

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
        with self._lock:
            session.tasks.append(task)
            try:
                session.next_seq = max(session.next_seq, int(task.id) + 1)
            except ValueError:
                session.next_seq = max(session.next_seq, len(session.tasks) + 1)
            self.save()
            return task

    def remove_task(self, session: SessionState, task: Task) -> None:
        with self._lock:
            session.tasks = [item for item in session.tasks if item.id != task.id]
            if not session.tasks and session.broadcast_time is None and session.broadcast_enabled:
                # keep session so last_broadcast_date / time overrides persist
                pass
            self.save()

    def mutate(self, fn: Callable[[], None]) -> None:
        with self._lock:
            fn()
            self.save()

    def next_id(self, session: SessionState) -> str:
        with self._lock:
            value = str(session.next_seq)
            session.next_seq += 1
            return value
