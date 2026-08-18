from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from typing import Any, Literal

TaskMode = Literal["countdown", "countup"]


def _filter_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {item.name for item in fields(cls)}
    return {key: value for key, value in data.items() if key in allowed}


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        payload = _filter_fields(cls, data)
        if payload.get("mode") not in {"countdown", "countup"}:
            payload["mode"] = "countdown"
        return cls(**payload)

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
        payload = asdict(self)
        payload["tasks"] = [task.to_dict() for task in self.tasks]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        payload = _filter_fields(cls, data)
        tasks = [Task.from_dict(item) for item in data.get("tasks", [])]
        payload["tasks"] = tasks
        payload.setdefault("key", data.get("umo", ""))
        payload.setdefault("umo", payload.get("key", ""))
        return cls(**payload)

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
        sessions = {
            key: SessionState.from_dict(value)
            for key, value in (data.get("sessions") or {}).items()
        }
        return cls(version=int(data.get("version", 1)), sessions=sessions)
