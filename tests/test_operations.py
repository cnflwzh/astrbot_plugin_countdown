from datetime import datetime

import pytest

from countdown.models import Task
from countdown.operations import create_task, edit_task
from countdown.parse import ParseError, parse_add_fields
from countdown.store import JsonStore


@pytest.fixture
def state(tmp_path):
    store = JsonStore(tmp_path / "data.json")
    session = store.ensure_session(
        "qq:GroupMessage:1", umo="qq:GroupMessage:1", platform_id="qq", group_id="1", is_group=True
    )
    return store, session


def _create(
    state, *, name="发布", target="2060-01-01 18:00", mode="countdown", limit=30, template=""
):
    now = datetime(2060, 1, 1, 9)
    name, parsed, template = parse_add_fields(
        name, target, template, now.date(), future_md=mode == "countdown"
    )
    return create_task(
        state[0],
        state[1],
        name=name,
        parsed_date=parsed,
        template=template,
        mode=mode,
        now=now,
        created_by="10001",
        limit=limit,
    )


def test_create_and_edit_keep_exact_structured_text(state):
    store, session = state
    task = _create(state, name="2026-10-01 release party", template='"{name}"\n{remain}')
    assert task.name == "2026-10-01 release party"
    assert task.target == "2060-01-01T18:00:00"
    assert task.template == '"{name}"\n{remain}'
    edit_task(
        store,
        session,
        target=task.name,
        field="template",
        value="新模板 {days:03d}",
        now=datetime(2060, 1, 1, 9),
    )
    store.load()
    loaded = store.get_session(session.key).tasks[0]
    assert loaded.template == "新模板 {days:03d}"
    assert loaded.revision == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "x" * 51},
        {"template": "x" * 201},
        {"target": "2059-12-31"},
        {"target": "2060-01-01 08:59"},
        {"target": "2060-01-02", "mode": "countup"},
    ],
)
def test_invalid_create_does_not_consume_id_or_write(state, kwargs):
    with pytest.raises(ParseError):
        _create(state, **kwargs)
    assert state[1].tasks == []
    assert state[1].next_seq == 1
    assert not state[0].path.exists()


def test_countup_same_day_date_only_and_task_limit(state):
    _create(state, name="开服", mode="countup", target="2059-12-01")
    _create(state, name="今天", target="2060-01-01")
    with pytest.raises(ParseError, match="上限"):
        _create(state, limit=2)
    with pytest.raises(ParseError, match="同名"):
        _create(state, name="今天")


def test_date_edit_resets_delivery_flags_and_rejects_past_without_mutation(state):
    store, session = state
    task = _create(state)
    task.pre_reminded = True
    task.due_reminded = True
    store.save()
    before = task.to_dict()
    with pytest.raises(ParseError):
        edit_task(
            store,
            session,
            target="1",
            field="date",
            value="2059-12-31",
            now=datetime(2060, 1, 1, 9),
        )
    assert task.to_dict() == before
    edit_task(
        store,
        session,
        target="1",
        field="date",
        value="2060-01-02 20:00",
        now=datetime(2060, 1, 1, 9),
    )
    assert not task.pre_reminded and not task.due_reminded
    assert task.revision == 1


def test_edit_is_isolated_to_selected_session(state):
    store, first = state
    task = _create(state)
    other = store.ensure_session(
        "qq:GroupMessage:2", umo="qq:GroupMessage:2", platform_id="qq", group_id="2", is_group=True
    )
    store.add_task(other, Task.from_dict(task.to_dict()))
    edit_task(store, other, target="1", field="enabled", value="关", now=datetime(2060, 1, 1, 9))
    assert first.tasks[0].enabled
    assert not other.tasks[0].enabled
