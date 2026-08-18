from __future__ import annotations

from pathlib import Path

from .render import RenderedItem

WIDTH = 920
PADDING = 36
HEADER_H = 148
ITEM_GAP = 16
ITEM_PAD_X = 20
ITEM_PAD_Y = 20
INDEX_SIZE = 44
REMAIN_W = 168


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


def _center_text(draw, center: tuple[float, float], text: str, font, fill) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(
        (center[0] - tw / 2 - box[0], center[1] - th / 2 - box[1]),
        text,
        font=font,
        fill=fill,
    )


def _remain_display(item: RenderedItem) -> tuple[str, str]:
    if item.is_due or (item.is_today and not item.has_time):
        return "今天", ""
    if item.remain:
        if item.remain.endswith("天") and item.remain[:-1].isdigit():
            return item.remain[:-1], "天"
        return item.remain, "剩余" if item.mode == "countdown" else "已过"
    if item.mode == "countdown":
        return str(max(item.days, 0)), "天"
    return f"+{max(item.days, 0)}", "天"


def render_card(path: Path, *, header: str, weekday: str, items: list[RenderedItem]) -> Path:
    from PIL import Image, ImageDraw

    title_font = _load_font(18)
    date_font = _load_font(38)
    week_font = _load_font(18)
    index_font = _load_font(20)
    name_font = _load_font(26)
    text_font = _load_font(18)
    meta_font = _load_font(16)
    remain_font = _load_font(28)
    remain_unit_font = _load_font(14)

    text_max = WIDTH - PADDING * 2 - ITEM_PAD_X * 2 - INDEX_SIZE - 20 - REMAIN_W
    heights: list[int] = []
    wrapped: list[tuple[list[str], list[str]]] = []
    for item in items:
        name_lines = _wrap(name_font, item.name, text_max)
        body_lines = _wrap(text_font, item.text, text_max)
        height = ITEM_PAD_Y * 2 + len(name_lines) * 34 + len(body_lines) * 26 + 26
        heights.append(max(height, 108))
        wrapped.append((name_lines, body_lines))

    footer_h = 44
    total_h = HEADER_H + PADDING + sum(heights) + ITEM_GAP * max(len(items) - 1, 0) + footer_h
    if not items:
        total_h += 80

    bg = (20, 22, 26)
    header_bg = (26, 29, 34)
    card = (34, 38, 46)
    card_today = (48, 40, 30)
    stroke = (58, 64, 74)
    gold = (212, 160, 84)
    cream = (244, 236, 220)
    muted = (154, 148, 138)
    ink = (28, 24, 20)
    shadow = (10, 11, 13)

    image = Image.new("RGB", (WIDTH, total_h), bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEADER_H), fill=header_bg)
    draw.rectangle((0, HEADER_H - 3, WIDTH, HEADER_H), fill=gold)

    draw.text((PADDING, 28), "COUNTDOWN · 倒计时", font=title_font, fill=gold)
    draw.text((PADDING, 58), header or "", font=date_font, fill=cream)
    if weekday:
        pill = f"  {weekday}  "
        pw = _width(week_font, pill) + 16
        px = WIDTH - PADDING - pw
        py = 66
        draw.rounded_rectangle((px, py, px + pw, py + 36), radius=18, outline=gold, width=1)
        _center_text(draw, (px + pw / 2, py + 18), weekday, week_font, gold)

    y = HEADER_H + 24
    for item, height, (name_lines, body_lines) in zip(items, heights, wrapped, strict=True):
        x0, x1 = PADDING, WIDTH - PADDING
        draw.rounded_rectangle((x0 + 3, y + 5, x1 + 3, y + height + 5), radius=18, fill=shadow)
        fill = card_today if item.is_today or item.is_due else card
        draw.rounded_rectangle((x0, y, x1, y + height), radius=18, fill=fill, outline=stroke, width=1)
        accent = gold if item.is_today or item.is_due else (72, 80, 92)
        draw.rounded_rectangle((x0, y, x0 + 7, y + height), radius=6, fill=accent)

        idx = item.index or 0
        cx, cy = x0 + ITEM_PAD_X + 8 + INDEX_SIZE / 2, y + height / 2
        draw.ellipse(
            (cx - INDEX_SIZE / 2, cy - INDEX_SIZE / 2, cx + INDEX_SIZE / 2, cy + INDEX_SIZE / 2),
            fill=gold if item.is_today or item.is_due else (232, 224, 208),
        )
        _center_text(draw, (cx, cy), str(idx or "-"), index_font, ink)

        text_x = x0 + ITEM_PAD_X + INDEX_SIZE + 24
        ty = y + ITEM_PAD_Y
        for name_line in name_lines:
            draw.text((text_x, ty), name_line, font=name_font, fill=cream)
            ty += 34
        for body_line in body_lines:
            draw.text((text_x, ty), body_line, font=text_font, fill=muted)
            ty += 26
        meta_bits = ["倒计时" if item.mode == "countdown" else "正计时"]
        if item.has_time and item.target_time:
            meta_bits.append(item.target_time)
        draw.text((text_x, ty + 2), " · ".join(meta_bits), font=meta_font, fill=(120, 116, 108))

        remain, unit = _remain_display(item)
        rx = x1 - ITEM_PAD_X - REMAIN_W / 2
        used_remain_font = remain_font if len(remain) <= 6 else text_font
        _center_text(draw, (rx, y + height / 2 - 8), remain, used_remain_font, gold)
        if unit:
            _center_text(draw, (rx, y + height / 2 + 20), unit, remain_unit_font, muted)
        y += height + ITEM_GAP

    count = len(items)
    draw.text(
        (PADDING, total_h - 32),
        f"{count} 项任务  ·  序号与 /倒计时 列表一致",
        font=meta_font,
        fill=(110, 106, 98),
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path
