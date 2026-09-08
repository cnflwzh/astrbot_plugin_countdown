from pathlib import Path

import pytest

from countdown.card import card_path, render_card
from countdown.render import RenderedItem


def test_render_card_writes_png(tmp_path: Path):
    path = tmp_path / "card.png"
    render_card(
        path,
        header="2060年1月1日",
        weekday="星期四",
        items=[
            RenderedItem(
                name="明日方舟：终末地",
                text="明日方舟：终末地就在今天！",
                days=0,
                mode="countdown",
                is_today=True,
                has_time=False,
                target_time="",
                index=2,
            ),
            RenderedItem(
                name="Dota3",
                text="距离《Dota3》发售还有30天",
                days=30,
                mode="countdown",
                is_today=False,
                has_time=True,
                target_time="18:00",
                remain="30天",
                index=1,
            ),
        ],
    )
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG")
    assert path.stat().st_size > 1000


def test_card_paths_do_not_collide_between_sessions(tmp_path):
    keys = [
        "bot-qq:GroupMessage:123",
        "bot_qq:GroupMessage:123",
        "x" * 90 + ":1",
        "x" * 90 + ":2",
        "../../outside",
    ]
    paths = [card_path(tmp_path, key) for key in keys]
    assert len(set(paths)) == len(keys)
    assert all(path.parent == tmp_path for path in paths)
    assert card_path(tmp_path, keys[0]) == paths[0]


def test_oversized_card_rejected_before_image_allocation(tmp_path, monkeypatch):
    from PIL import Image

    def fail_new(*args, **kwargs):
        pytest.fail("oversized image must not be allocated")

    monkeypatch.setattr(Image, "new", fail_new)
    item = RenderedItem("x", "x", 1, "countdown", False, False, "")
    with pytest.raises(ValueError, match="too large"):
        render_card(tmp_path / "huge.png", header="date", weekday="day", items=[item] * 1000)
    assert not (tmp_path / "huge.png").exists()
