from pathlib import Path

from countdown.card import render_card
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
