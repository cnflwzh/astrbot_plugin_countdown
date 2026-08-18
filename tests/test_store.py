from pathlib import Path

from countdown.models import Task
from countdown.store import JsonStore


def test_store_roundtrip(tmp_path: Path):
    path = tmp_path / "data.json"
    store = JsonStore(path)
    store.load()
    session = store.ensure_session(
        "aiocqhttp:GroupMessage:123",
        umo="aiocqhttp:GroupMessage:123",
        platform_id="aiocqhttp",
        group_id="123",
        is_group=True,
    )
    task = Task(
        id=store.next_id(session),
        name="Dota3",
        mode="countdown",
        target="2060-01-31",
        template="距离{name}还有{days}天",
        created_by="10001",
        created_at="2026-08-18T09:00:00",
    )
    store.add_task(session, task)

    reloaded = JsonStore(path)
    reloaded.load()
    loaded = reloaded.get_session("aiocqhttp:GroupMessage:123")
    assert loaded is not None
    assert loaded.group_id == "123"
    assert loaded.tasks[0].name == "Dota3"
    assert loaded.tasks[0].target_date().isoformat() == "2060-01-31"
    assert loaded.next_seq == 2
