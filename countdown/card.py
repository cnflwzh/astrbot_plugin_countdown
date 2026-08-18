from __future__ import annotations

from pathlib import Path

from .render import RenderedItem

WIDTH = 840
PADDING = 40
HEADER_H = 132
ITEM_GAP = 14
ITEM_PAD = 22


def _font_candidates() -> list[str]:
    return [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
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


def _load_font(size: int):
    from PIL import ImageFont

    for path in _font_candidates():
        font_path = Path(path)
        if not font_path.exists():
            continue
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _width(font, text: str) -> float:
    if hasattr(font, "getlength"):
        return float(font.getlength(text))
    box = font.getbbox(text)
    return float(box[2] - box[0])


def _wrap(font, text: str, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if _width(font, trial) <= max_width or not current:
            current = trial
            continue
        lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines or [""]


def render_card(path: Path, *, header: str, weekday: str, items: list[RenderedItem]) -> Path:
    from PIL import Image, ImageDraw

    title_font = _load_font(22)
    date_font = _load_font(36)
    week_font = _load_font(20)
    days_font = _load_font(40)
    name_font = _load_font(26)
    text_font = _load_font(20)
    badge_font = _load_font(16)

    inner_w = WIDTH - PADDING * 2
    item_inner_w = inner_w - ITEM_PAD * 2 - 108
    heights: list[int] = []
    wrapped: list[tuple[list[str], list[str]]] = []
    for item in items:
        name_lines = _wrap(name_font, item.name, item_inner_w)
        body_lines = _wrap(text_font, item.text, item_inner_w)
        height = ITEM_PAD * 2 + len(name_lines) * 34 + len(body_lines) * 28 + 8
        heights.append(max(height, 96))
        wrapped.append((name_lines, body_lines))

    total_h = HEADER_H + PADDING + sum(heights) + ITEM_GAP * max(len(items) - 1, 0) + PADDING
    if not items:
        total_h += 80

    paper = (246, 241, 232)
    header_bg = (28, 37, 48)
    ink = (36, 32, 28)
    muted = (122, 114, 106)
    today = (184, 72, 44)
    card_bg = (255, 252, 247)
    card_line = (220, 210, 196)

    image = Image.new("RGB", (WIDTH, total_h), paper)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEADER_H), fill=header_bg)
    draw.text((PADDING, 28), "倒计时", font=title_font, fill=(214, 196, 168))
    draw.text((PADDING, 58), header or "", font=date_font, fill=(250, 246, 238))
    if weekday:
        ww = _width(week_font, weekday)
        draw.text((WIDTH - PADDING - ww, 70), weekday, font=week_font, fill=(184, 176, 164))

    y = HEADER_H + PADDING
    for item, height, (name_lines, body_lines) in zip(items, heights, wrapped, strict=True):
        draw.rounded_rectangle(
            (PADDING, y, WIDTH - PADDING, y + height),
            radius=16,
            fill=card_bg,
            outline=card_line,
            width=1,
        )
        accent = today if item.is_today else header_bg
        draw.rounded_rectangle((PADDING, y, PADDING + 8, y + height), radius=8, fill=accent)

        if item.is_due or (item.is_today and not item.has_time):
            badge = "今天"
        elif item.has_time and item.is_today:
            badge = item.remain or item.target_time or "今天"
        elif item.mode == "countdown":
            badge = f"{max(item.days, 0)}"
        else:
            badge = f"+{max(item.days, 0)}"
        badge_color = today if item.is_today or item.is_due else header_bg
        draw.text(
            (PADDING + 28, y + 22),
            badge,
            font=days_font if len(badge) <= 3 else badge_font,
            fill=badge_color,
        )

        text_x = PADDING + 120
        ty = y + ITEM_PAD
        for line in name_lines:
            draw.text((text_x, ty), line, font=name_font, fill=ink)
            ty += 34
        for line in body_lines:
            draw.text((text_x, ty), line, font=text_font, fill=muted)
            ty += 28
        if item.has_time and item.target_time:
            label = item.target_time
            lw = _width(badge_font, label)
            draw.text((WIDTH - PADDING - ITEM_PAD - lw, y + 18), label, font=badge_font, fill=muted)
        y += height + ITEM_GAP

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path
