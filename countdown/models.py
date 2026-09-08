from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from typing import Any, Literal

TaskMode = Literal["countdown", "countup"]


def _filter_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{cls.__name__} must be an object")
    allowed = {item.name for item in fields(cls)}
    return {key: value for key, value in data.items() if key in allowed}


def _validate_types(obj: Any, **expected: type) -> None:
    for name, kind in expected.items():
        if type(getattr(obj, name)) is not kind:
            raise ValueError(f"invalid {type(obj).__name__}.{name}")


@dataclass
class Task:
    id: str
    name: str
    mode: TaskMode
    target: str
    template: str
    created_by: str
    created_at: str
    enabled: bool = True
    has_time: bool = False
    pre_reminded: bool = False
    due_reminded: bool = False
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        payload = _filter_fields(cls, data)
        task = cls(**payload)
        _validate_types(
            task,
            id=str,
            name=str,
            mode=str,
            target=str,
            template=str,
            created_by=str,
            created_at=str,
            enabled=bool,
            has_time=bool,
            pre_reminded=bool,
            due_reminded=bool,
            revision=int,
        )
        if not task.id or not task.name.strip() or task.mode not in {"countdown", "countup"}:
            raise ValueError("invalid task id, name or mode")
        if task.revision < 0:
            raise ValueError("invalid task revision")
        if "has_time" not in payload and "T" in task.target:
            task.has_time = True
        if task.target_datetime().tzinfo is not None:
            raise ValueError("task target must use local time without an offset")
        return task

    def target_datetime(self) -> datetime:
        raw = self.target.strip()
        if self.has_time or "T" in raw:
            return datetime.fromisoformat(raw)
        return datetime.fromisoformat(f"{raw}T00:00:00")

    def target_date(self) -> date:
        return self.target_datetime().date()


@dataclass
class SessionState:
    key: str
    umo: str
    platform_id: str
    group_id: str = ""
    is_group: bool = True
    broadcast_time: str | None = None
    broadcast_enabled: bool = True
    last_broadcast_date: str | None = None
    next_seq: int = 1
    tasks: list[Task] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        payload = _filter_fields(cls, data)
        if not isinstance(data.get("tasks", []), list):
            raise ValueError("session tasks must be a list")
        tasks = [Task.from_dict(item) for item in data.get("tasks", [])]
        payload["tasks"] = tasks
        payload.setdefault("key", data.get("umo", ""))
        payload.setdefault("umo", payload.get("key", ""))
        session = cls(**payload)
        _validate_types(
            session,
            key=str,
            umo=str,
            platform_id=str,
            group_id=str,
            is_group=bool,
            broadcast_enabled=bool,
            next_seq=int,
        )
        if not session.key or not session.umo or not session.platform_id or session.next_seq < 1:
            raise ValueError("invalid session identity or sequence")
        if session.broadcast_time is not None:
            from .parse import parse_clock

            parse_clock(session.broadcast_time)
        if session.last_broadcast_date is not None:
            date.fromisoformat(session.last_broadcast_date)
        if len({task.id for task in tasks}) != len(tasks):
            raise ValueError("duplicate task ids")
        for task in tasks:
            if task.id.isascii() and task.id.isdecimal():
                session.next_seq = max(session.next_seq, int(task.id) + 1)
        return session

    def enabled_tasks(self) -> list[Task]:
        return [task for task in self.tasks if task.enabled]


@dataclass
class StoreData:
    version: int = 1
    sessions: dict[str, SessionState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "sessions": {key: session.to_dict() for key, session in self.sessions.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoreData:
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
            raise ValueError("store and sessions must be objects")
        version = data.get("version", 1)
        if type(version) is not int or version != 1:
            raise ValueError("unsupported store version")
        sessions = {
            key: SessionState.from_dict(value) for key, value in data.get("sessions", {}).items()
        }
        if any(key != session.key for key, session in sessions.items()):
            raise ValueError("session key does not match its stored identity")
        return cls(version=version, sessions=sessions)
