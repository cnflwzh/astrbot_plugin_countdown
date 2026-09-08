import json
from pathlib import Path

import pytest

from countdown.models import SessionState, Task
from countdown.store import JsonStore, StoreError


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


@pytest.mark.parametrize(
    "raw",
    [
        '{"sessions":',
        '{"sessions": []}',
        "[]",
        '{"sessions": null}',
        "{}",
        '{"version": 1}',
        '{"version": 2, "sessions": {}}',
        '{"sessions": {}, "sessions": {}}',
    ],
)
def test_invalid_store_is_never_silently_overwritten(tmp_path, raw):
    path = tmp_path / "data.json"
    path.write_text(raw, encoding="utf-8")
    store = JsonStore(path)
    with pytest.raises(StoreError, match="data.json"):
        store.load()
    with pytest.raises(StoreError, match="data.json"):
        store.save()
    assert path.read_text(encoding="utf-8") == raw


def test_failed_save_restores_live_objects(tmp_path, monkeypatch):
    store = JsonStore(tmp_path / "data.json")
    session = store.ensure_session(
        "qq:GroupMessage:1", umo="qq:GroupMessage:1", platform_id="qq", group_id="1", is_group=True
    )
    task = Task("1", "原名称", "countdown", "2060-01-01", "", "1", "2026-01-01")
    store.add_task(session, task)
    original = store.path.read_bytes()

    def fail_replace(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="disk unavailable"):
        store.mutate(lambda: setattr(task, "name", "新名称"))
    assert store.get_session(session.key) is session
    assert session.tasks[0] is task
    assert task.name == "原名称"
    with pytest.raises(OSError):
        store.remove_task(session, task)
    assert session.tasks == [task]
    added = Task("2", "新增", "countdown", "2060-01-01", "", "1", "2026-01-01")
    with pytest.raises(OSError):
        store.add_task(session, added)
    assert session.tasks == [task]
    assert session.next_seq == 2
    assert store.path.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def _legacy_data():
    task = Task(
        "7", "发布", "countdown", "2060-01-01T18:00:00", "", "1", "2026-01-01", has_time=True
    )
    session = SessionState(
        "qq:GroupMessage:1", "qq:GroupMessage:1", "qq", group_id="1", tasks=[task]
    )
    data = session.to_dict()
    del data["tasks"][0]["revision"]
    data["tasks"][0]["future_field"] = "ignored"
    return {"version": 1, "sessions": {session.key: data}}, session.key


def test_legacy_data_loads_and_sequence_cannot_reuse_id(tmp_path):
    raw, key = _legacy_data()
    path = tmp_path / "data.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    store = JsonStore(path)
    store.load()
    session = store.get_session(key)
    assert session.tasks[0].revision == 0
    assert session.tasks[0].has_time
    assert store.next_id(session) == "8"


@pytest.mark.parametrize(
    "field, value",
    [
        ("target", "broken"),
        ("target", "2060-01-01T18:00:00+08:00"),
        ("enabled", "false"),
        ("mode", "unknown"),
        ("revision", -1),
    ],
)
def test_invalid_task_data_cannot_poison_scheduler_or_overwrite_file(tmp_path, field, value):
    raw, key = _legacy_data()
    raw["sessions"][key]["tasks"][0][field] = value
    path = tmp_path / "data.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    before = path.read_bytes()
    store = JsonStore(path)
    with pytest.raises(StoreError):
        store.load()
    with pytest.raises(StoreError):
        store.save()
    assert path.read_bytes() == before


def test_duplicate_ids_cannot_delete_multiple_tasks(tmp_path):
    raw, key = _legacy_data()
    raw["sessions"][key]["tasks"] *= 2
    path = tmp_path / "data.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(StoreError):
        JsonStore(path).load()


def test_store_recovers_only_after_valid_file_is_restored(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("broken", encoding="utf-8")
    store = JsonStore(path)
    with pytest.raises(StoreError):
        store.load()
    raw, key = _legacy_data()
    path.write_text(json.dumps(raw), encoding="utf-8")
    store.load()
    store.save()
    assert store.get_session(key).tasks[0].name == "发布"


def test_missing_session_identity_does_not_create_shared_empty_session(tmp_path):
    store = JsonStore(tmp_path / "data.json")
    with pytest.raises(ValueError, match="identity"):
        store.ensure_session("", umo="", platform_id="qq", group_id="", is_group=False)
    assert store.iter_sessions() == []
