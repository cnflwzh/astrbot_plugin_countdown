from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .render import MAX_TEMPLATE_OUTPUT, RenderedItem

WIDTH = 1000
PADDING = 44
ROW_PADDING = 32
DIVIDER_X = WIDTH - PADDING - 220
TEXT_X = PADDING + ROW_PADDING
TEXT_WIDTH = DIVIDER_X - TEXT_X - ROW_PADDING
MAX_CARD_PIXELS = 12_000_000

PAPER = "#F3F2ED"
SURFACE = "#FFFFFF"
INK = "#243D34"
MUTED = "#7D877F"
LINE = "#E8EBE5"
GREEN = "#275C49"
AMBER = "#B66C32"
TEAL = "#3B7773"
_REMAIN_PARTS = re.compile(r"(\d+)(天|小时|分钟)")


def card_path(directory: Path, key: str) -> Path:
    return directory / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.png"


def _font_candidates(*, bold: bool = False, number: bool = False) -> list[str]:
    candidates = []
    if number:
        candidates.extend(
            [
                r"C:\Windows\Fonts\bahnschrift.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
            ]
        )
    if bold:
        candidates.extend(
            [
                r"C:\Windows\Fonts\msyhbd.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            ]
        )
    return candidates + [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]


@lru_cache(maxsize=48)
def _load_font(size: int, *, bold: bool = False, number: bool = False):
    from PIL import ImageFont

    for candidate in _font_candidates(bold=bold, number=number):
        if not Path(candidate).is_file():
            continue
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Pillow 10.0 does not accept the size argument for its built-in font.
        return ImageFont.load_default()


def _width(font, text: str) -> float:
    if hasattr(font, "getlength"):
        return float(font.getlength(text))
    bounds = font.getbbox(text)
    return float(bounds[2] - bounds[0])


def _wrap(font, text: str, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        current = ""
        for char in paragraph:
            trial = current + char
            if current and (len(current) >= 256 or _width(font, trial) > max_width):
                lines.append(current)
                current = char
            else:
                current = trial
        lines.append(current)
    return lines


class _Canvas:
    """Draw in layout units, with optional supersampling for smooth small cards."""

    def __init__(self, image, scale: int):
        from PIL import ImageDraw

        self.draw = ImageDraw.Draw(image)
        self.scale = scale

    def rounded(self, box, *, radius: int, fill: str, outline: str | None = None):
        self.draw.rounded_rectangle(
            tuple(round(value * self.scale) for value in box),
            radius=radius * self.scale,
            fill=fill,
            outline=outline,
            width=self.scale,
        )

    def line(self, points, fill: str, width: int = 1):
        self.draw.line(
            [(round(x * self.scale), round(y * self.scale)) for x, y in points],
            fill=fill,
            width=width * self.scale,
        )

    def measure(self, text: str, size: int, *, bold: bool = False, number: bool = False):
        font = _load_font(size * self.scale, bold=bold, number=number)
        bounds = font.getbbox(text)
        return _width(font, text) / self.scale, (bounds[3] - bounds[1]) / self.scale

    def text(
        self,
        x: float,
        y: float,
        text: str,
        size: int,
        fill: str,
        *,
        bold: bool = False,
        number: bool = False,
        centered: bool = False,
    ):
        font = _load_font(size * self.scale, bold=bold, number=number)
        if centered:
            x -= _width(font, text) / self.scale / 2
        self.draw.text(
            (round(x * self.scale), round(y * self.scale)),
            text,
            font=font,
            fill=fill,
            anchor="lt",
        )

    def fitted_size(
        self,
        text: str,
        width: float,
        size: int,
        minimum: int,
        *,
        number: bool = False,
    ) -> int:
        measured, _ = self.measure(text, size, bold=True, number=number)
        if measured > width:
            size = max(minimum, int(size * width / max(measured, 1)))
        while size > minimum and self.measure(text, size, bold=True, number=number)[0] > width:
            size -= 1
        return size


@dataclass
class _Row:
    item: RenderedItem
    name_lines: list[str]
    body_lines: list[str]
    height: int


def _status(item: RenderedItem) -> tuple[str, str, str]:
    if item.mode == "countup":
        label, color, background = "正计时", TEAL, "#E9F3F0"
    elif item.is_due or (item.is_today and not item.has_time):
        label, color, background = "今日到期", AMBER, "#FCEDDC"
    elif item.is_today:
        label, color, background = "今天", AMBER, "#FCEDDC"
    else:
        label, color, background = "倒计时", GREEN, "#EFF3EE"
    if item.has_time and item.target_time:
        label += f"  ·  {item.target_time}"
    return label, color, background


def _remain_display(item: RenderedItem) -> tuple[str, str]:
    if item.is_due or (item.is_today and not item.has_time):
        return "今天", ""
    if item.remain:
        if item.remain.endswith("天") and item.remain[:-1].isdigit():
            return item.remain[:-1], "天"
        return item.remain, "剩余" if item.mode == "countdown" else "已过"
    return str(max(item.days, 0)), "天"


def _draw_remaining(canvas: _Canvas, row: _Row, top: int, color: str) -> None:
    item = row.item
    value, unit = _remain_display(item)
    secondary = ""
    if unit in {"剩余", "已过"}:
        parts = _REMAIN_PARTS.findall(value)
        if parts and "".join(number + label for number, label in parts) == value:
            value, unit = parts[0]
            secondary = "  ".join(number + label for number, label in parts[1:])
        else:
            unit = ""
    caption = "已累计" if item.mode == "countup" else "还剩"
    if value == "今天":
        caption = "已到时间" if item.has_time else "就在今天"
    center = (DIVIDER_X + WIDTH - PADDING) / 2
    unit_width, unit_height = canvas.measure(unit, 19) if unit else (0, 0)
    gap = 7 if unit else 0
    size = canvas.fitted_size(
        value,
        182 - unit_width - gap,
        70 if value.isdecimal() else 42,
        22,
        number=value.isdecimal(),
    )
    value_width, value_height = canvas.measure(value, size, bold=True, number=value.isdecimal())
    height = 16 + 16 + value_height + (32 if secondary else 0)
    y = top + (row.height - height) / 2
    canvas.text(center, y, caption, 15, MUTED, centered=True)
    y += 32
    x = center - (value_width + gap + unit_width) / 2
    canvas.text(x, y, value, size, color, bold=True, number=value.isdecimal())
    if unit:
        canvas.text(x + value_width + gap, y + value_height - unit_height - 2, unit, 19, color)
    if secondary:
        secondary_size = canvas.fitted_size(secondary, 184, 19, 14)
        canvas.text(center, y + value_height + 13, secondary, secondary_size, color, centered=True)


def _draw_row(canvas: _Canvas, row: _Row, top: int, *, last: bool) -> None:
    item = row.item
    label, color, background = _status(item)
    index = f"{item.index:02d}" if item.index > 0 else "—"
    canvas.text(TEXT_X, top + 27, index, 17, "#9BA59D", number=True)
    label_x = TEXT_X + 40
    label_width, _ = canvas.measure(label, 14)
    canvas.rounded(
        (label_x, top + 22, label_x + label_width + 22, top + 49),
        radius=7,
        fill=background,
    )
    canvas.text(label_x + 11, top + 28, label, 14, color)
    y = top + 64
    for line in row.name_lines:
        canvas.text(TEXT_X, y, line, 30, INK, bold=True)
        y += 40
    y += 8
    for line in row.body_lines:
        canvas.text(TEXT_X, y, line, 20, MUTED)
        y += 28
    canvas.line([(DIVIDER_X, top + 34), (DIVIDER_X, top + row.height - 34)], LINE)
    _draw_remaining(canvas, row, top, color)
    if not last:
        canvas.line(
            [(TEXT_X, top + row.height), (WIDTH - PADDING - ROW_PADDING, top + row.height)], LINE
        )


def render_card(path: Path, *, header: str, weekday: str, items: list[RenderedItem]) -> Path:
    from PIL import Image

    if len(header) > MAX_TEMPLATE_OUTPUT or len(weekday) > 32:
        raise ValueError("card header is too large")
    week_width = _width(_load_font(18), weekday) + 32 if weekday else 0
    header_lines = _wrap(
        _load_font(42, bold=True), header or "倒计时", WIDTH - 2 * PADDING - week_width - 28
    )
    summary_y = 94 + len(header_lines) * 54 + 19
    panel_y = summary_y + 52
    rows: list[_Row] = []
    content_height = 0
    for item in items:
        if len(item.name) > MAX_TEMPLATE_OUTPUT or len(item.text) > MAX_TEMPLATE_OUTPUT:
            raise ValueError("card text is too large")
        names = _wrap(_load_font(30, bold=True), item.name, TEXT_WIDTH)
        body = _wrap(_load_font(20), item.text, TEXT_WIDTH) if item.text else []
        height = max(180, 64 + len(names) * 40 + (8 + len(body) * 28 if body else 0) + 30)
        content_height += height
        if WIDTH * (panel_y + content_height + 82) > MAX_CARD_PIXELS:
            raise ValueError("card is too large; use the text fallback")
        rows.append(_Row(item, names, body, height))
    panel_height = content_height or 196
    total_height = panel_y + panel_height + 82
    if WIDTH * total_height > MAX_CARD_PIXELS:
        raise ValueError("card is too large; use the text fallback")

    # Stay within the same pixel budget, including the antialiasing canvas.
    scale = 2 if WIDTH * total_height * 4 <= MAX_CARD_PIXELS else 1
    image = Image.new("RGB", (WIDTH * scale, total_height * scale), PAPER)
    canvas = _Canvas(image, scale)

    canvas.rounded((PADDING, 47, PADDING + 24, 52), radius=2, fill=GREEN)
    canvas.text(PADDING + 36, 43, "C O U N T D O W N   /   每日一览", 14, GREEN)
    y = 94
    for line in header_lines:
        canvas.text(PADDING, y, line, 42, INK, bold=True)
        y += 54
    if weekday:
        week_x = WIDTH - PADDING - week_width
        canvas.rounded((week_x, 96, WIDTH - PADDING, 134), radius=19, fill="#E6EBE3")
        canvas.text(week_x + week_width / 2, 106, weekday, 18, GREEN, centered=True)
    today_count = sum(item.mode == "countdown" and (item.is_today or item.is_due) for item in items)
    summary = f"{len(items):02d} 项任务"
    if today_count:
        summary += f"   /   {today_count} 项就在今天"
    canvas.text(PADDING, summary_y, summary, 17, MUTED)

    panel_box = (PADDING, panel_y, WIDTH - PADDING, panel_y + panel_height)
    canvas.rounded(
        (PADDING, panel_y + 5, WIDTH - PADDING, panel_y + panel_height + 5),
        radius=24,
        fill="#E9EBE3",
    )
    canvas.rounded(panel_box, radius=24, fill=SURFACE, outline="#E6E9E1")
    y = panel_y
    for index, row in enumerate(rows):
        _draw_row(canvas, row, y, last=index == len(rows) - 1)
        y += row.height
    if not rows:
        canvas.text(WIDTH / 2, panel_y + 56, "今天还没有日程", 28, INK, bold=True, centered=True)
        canvas.text(
            WIDTH / 2,
            panel_y + 104,
            "用 /倒计时 添加，记下下一个值得期待的日子。",
            18,
            MUTED,
            centered=True,
        )

    footer_y = panel_y + panel_height + 31
    canvas.rounded((PADDING, footer_y + 4, PADDING + 6, footer_y + 10), radius=3, fill="#8AA294")
    canvas.text(PADDING + 17, footer_y, "序号与 /倒计时 列表一致", 14, MUTED)
    canvas.text(WIDTH - PADDING - 105, footer_y + 1, "每一天，都算数", 14, "#99A196")

    if scale > 1:
        reduced = image.resize((WIDTH, total_height), Image.Resampling.LANCZOS)
        image.close()
        image = reduced
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image.save(path, format="PNG")
    finally:
        image.close()
    return path
