from datetime import datetime

from countdown.models import Task
from countdown.render import (
    header_context,
    render_broadcast,
    render_template,
    task_context,
)


def _task(name: str, mode: str, target: str, template: str = "") -> Task:
    return Task(
        id="1",
        name=name,
        mode=mode,  # type: ignore[arg-type]
        target=target,
        template=template,
        created_by="1",
        created_at="2026-01-01T00:00:00",
    )


def test_header_and_item_templates_match_example():
    now = datetime(2060, 1, 1, 9, 0, 0)
    header = render_template("今天是{year}年{month}月{day}日。", header_context(now))
    assert header == "今天是2060年1月1日。"

    dota = _task("Dota3", "countdown", "2060-01-31", "距离《{name}》发售还有{days}天")
    ark = _task("明日方舟：终末地", "countdown", "2060-01-01", "《{name}》30.0 前瞻还有{days}天")
    text = render_broadcast(
        [dota, ark],
        now,
        header_template="今天是{year}年{month}月{day}日。",
        countdown_template="距离{name}还有{days}天",
        countup_template="{name}已经过去{days}天",
        item_prefix="- ",
    )
    assert text == (
        "今天是2060年1月1日。\n- 明日方舟：终末地就在今天！\n- 距离《Dota3》发售还有30天"
    )


def test_today_template_overrides_custom_item():
    now = datetime(2060, 1, 1, 9, 0, 0)
    task = _task("Dota3", "countdown", "2060-01-01", "距离{name}发售还有{days}天")
    text = render_broadcast(
        [task],
        now,
        header_template="",
        countdown_template="距离{name}还有{days}天",
        countup_template="{name}已经过去{days}天",
        today_template="{name}就在今天！",
        item_prefix="",
    )
    assert text == "Dota3就在今天！"


def test_unknown_placeholder_kept():
    assert render_template("hello {missing}", {"name": "x"}) == "hello {missing}"


def test_countup_days():
    now = datetime(2026, 8, 18, 9, 0, 0)
    task = _task("开服", "countup", "2026-08-08")
    ctx = task_context(task, now)
    assert ctx["days"] == 10
    assert ctx["mode"] == "正计时"


def test_timed_countdown_uses_remain_before_due():
    now = datetime(2026, 8, 21, 9, 0, 0)
    task = Task(
        id="1",
        name="《明日方舟：终末地》前瞻",
        mode="countdown",
        target="2026-08-21T19:30:00",
        template="",
        created_by="1",
        created_at="2026-08-18T09:00:00",
        has_time=True,
    )
    text = render_broadcast(
        [task],
        now,
        header_template="",
        countdown_template="距离{name}还有{days}天",
        countup_template="{name}已经过去{days}天",
        today_template="{name}就在今天！",
        item_prefix="",
    )
    assert text == "距离《明日方舟：终末地》前瞻还有10小时30分钟"
    ctx = task_context(task, now)
    assert ctx["target"] == "2026年8月21日 19:30"
    assert ctx["remain"] == "10小时30分钟"

    after = render_broadcast(
        [task],
        datetime(2026, 8, 21, 19, 30, 0),
        header_template="",
        countdown_template="距离{name}还有{days}天",
        countup_template="{name}已经过去{days}天",
        today_template="{name}就在今天！",
        item_prefix="",
    )
    assert after == "《明日方舟：终末地》前瞻就在今天！"
