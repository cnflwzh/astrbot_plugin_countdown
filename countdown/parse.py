from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

COMMAND_ALIASES = ("倒计时", "countdown", "cd")
SUBCOMMANDS = {
    "添加": "add",
    "add": "add",
    "新建": "add",
    "正计时": "countup",
    "up": "countup",
    "countup": "countup",
    "列表": "list",
    "list": "list",
    "ls": "list",
    "删除": "delete",
    "del": "delete",
    "delete": "delete",
    "rm": "delete",
    "改": "edit",
    "编辑": "edit",
    "edit": "edit",
    "查询": "query",
    "播报": "query",
    "now": "query",
    "query": "query",
    "时间": "time",
    "time": "time",
    "开关": "toggle",
    "toggle": "toggle",
    "开启": "enable",
    "enable": "enable",
    "on": "enable",
    "关闭": "disable",
    "disable": "disable",
    "off": "disable",
    "帮助": "help",
    "help": "help",
    "?": "help",
}

_DATE_PATTERNS = [
    re.compile(
        r"^(?P<y>\d{4})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})"
        r"(?:[T\s]?(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?)?$"
    ),
    re.compile(
        r"^(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日?"
        r"(?:[T\s]?(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?)?$"
    ),
    re.compile(
        r"^(?P<m>\d{1,2})月(?P<d>\d{1,2})日?"
        r"(?:[T\s]?(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?)?$"
    ),
    re.compile(
        r"^(?P<m>\d{1,2})[-/.](?P<d>\d{1,2})"
        r"(?:[T\s](?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?)?$"
    ),
]
_TIME_PATTERN = re.compile(r"^(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?$")
_HM_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


class ParseError(ValueError):
    pass


@dataclass
class ParsedCommand:
    sub: str
    rest: str
    tokens: list[str]


@dataclass
class ParsedDate:
    value: datetime
    has_time: bool
    iso: str


def extract_after_command(message_str: str) -> str:
    text = (message_str or "").strip()
    if text.startswith("/"):
        text = text[1:].lstrip()
    for alias in COMMAND_ALIASES:
        if text == alias:
            return ""
        prefix = alias + " "
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
        if alias.isascii() and text.lower().startswith(alias.lower() + " "):
            return text[len(alias) :].strip()
        if alias.isascii() and text.lower() == alias.lower():
            return ""
    return text


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            j = i + 1
            buf: list[str] = []
            while j < n and text[j] != quote:
                buf.append(text[j])
                j += 1
            tokens.append("".join(buf))
            i = j + 1 if j < n else n
            continue
        if ch == "《":
            j = text.find("》", i + 1)
            if j != -1:
                tokens.append(text[i : j + 1])
                i = j + 1
                continue
        j = i + 1
        while j < n and not text[j].isspace():
            j += 1
        tokens.append(text[i:j])
        i = j
    return tokens


def parse_command(message_str: str) -> ParsedCommand:
    rest = extract_after_command(message_str)
    tokens = tokenize(rest)
    if not tokens:
        return ParsedCommand(sub="help", rest="", tokens=[])
    raw_sub = tokens[0]
    sub = SUBCOMMANDS.get(raw_sub, SUBCOMMANDS.get(raw_sub.lower(), ""))
    if not sub:
        raise ParseError(f"未知子命令「{raw_sub}」。发送 /倒计时 帮助 查看用法。")
    remain_tokens = tokens[1:]
    remain = rest[len(raw_sub) :].strip() if rest.startswith(raw_sub) else " ".join(remain_tokens)
    return ParsedCommand(sub=sub, rest=remain, tokens=remain_tokens)


def parse_clock(text: str) -> tuple[int, int]:
    raw = (text or "").strip()
    match = _HM_PATTERN.fullmatch(raw)
    if not match:
        raise ParseError("时间格式应为 HH:MM，例如 09:00 或 21:30。")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ParseError("时间超出范围，小时为 0-23，分钟为 0-59。")
    return hour, minute


def format_clock(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _resolve_md_year(parsed: date, today: date, *, future_md: bool, has_year: bool) -> date:
    if has_year:
        return parsed
    month, day = parsed.month, parsed.day
    if future_md and parsed < today:
        try:
            return date(today.year + 1, month, day)
        except ValueError as exc:
            raise ParseError(f"无效日期：{month}月{day}日") from exc
    if not future_md and parsed > today:
        try:
            return date(today.year - 1, month, day)
        except ValueError as exc:
            raise ParseError(f"无效日期：{month}月{day}日") from exc
    return parsed


def _parse_date_token(token: str, today: date, *, future_md: bool) -> tuple[date, tuple[int, int, int] | None] | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.fullmatch(token)
        if not match:
            continue
        parts = match.groupdict()
        year = int(parts["y"]) if parts.get("y") else today.year
        month = int(parts["m"])
        day = int(parts["d"])
        try:
            parsed = date(year, month, day)
        except ValueError as exc:
            raise ParseError(f"无效日期：{token}") from exc
        parsed = _resolve_md_year(parsed, today, future_md=future_md, has_year=bool(parts.get("y")))
        glued_time = None
        if parts.get("H") is not None:
            hour = int(parts["H"])
            minute = int(parts["M"])
            second = int(parts["S"] or 0)
            if hour > 23 or minute > 59 or second > 59:
                raise ParseError(f"无效时间：{token}")
            glued_time = (hour, minute, second)
        return parsed, glued_time
    return None


def _parse_time_token(token: str) -> tuple[int, int, int] | None:
    match = _TIME_PATTERN.fullmatch(token)
    if not match:
        return None
    hour = int(match.group("H"))
    minute = int(match.group("M"))
    second = int(match.group("S") or 0)
    if hour > 23 or minute > 59 or second > 59:
        raise ParseError(f"无效时间：{token}")
    return hour, minute, second


def parse_datetime(
    tokens: list[str], today: date, *, future_md: bool
) -> tuple[ParsedDate, list[str]]:
    if not tokens:
        raise ParseError("缺少日期，例如 2026-12-31 或 2026年12月31日19:30。")
    matched = _parse_date_token(tokens[0], today, future_md=future_md)
    if matched is None:
        raise ParseError(
            f"无法识别日期「{tokens[0]}」。支持 2026-12-31 / 2026年12月31日 / 2026年8月21日19:30。"
        )
    parsed_date, glued_time = matched
    consumed = 1
    has_time = False
    hour = minute = second = 0
    if glued_time is not None:
        hour, minute, second = glued_time
        has_time = True
    elif len(tokens) >= 2:
        parsed_time = _parse_time_token(tokens[1])
        if parsed_time is not None:
            hour, minute, second = parsed_time
            has_time = True
            consumed = 2
    value = datetime(parsed_date.year, parsed_date.month, parsed_date.day, hour, minute, second)
    iso = value.isoformat(timespec="seconds") if has_time else parsed_date.isoformat()
    return ParsedDate(value=value, has_time=has_time, iso=iso), tokens[consumed:]


def join_name(parts: list[str]) -> str:
    name = ""
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        if not name:
            name = piece
        elif name.endswith("》") or piece.startswith("《"):
            name += piece
        else:
            name += " " + piece
    return name


def find_datetime_index(tokens: list[str], today: date, *, future_md: bool) -> int:
    for index, token in enumerate(tokens):
        try:
            if _parse_date_token(token, today, future_md=future_md) is not None:
                return index
        except ParseError:
            continue
    return -1


def parse_add_args(
    tokens: list[str], today: date, *, future_md: bool
) -> tuple[str, ParsedDate, str]:
    if not tokens:
        raise ParseError("用法：/倒计时 添加 <名称> <日期或日期时间> [模板]")
    index = find_datetime_index(tokens, today, future_md=future_md)
    if index < 0:
        raise ParseError("缺少日期。例如：/倒计时 添加 《明日方舟：终末地》前瞻 2026年8月21日19:30")
    if index == 0:
        raise ParseError("缺少名称，请写在日期前面。")
    name = join_name(tokens[:index])
    if not name:
        raise ParseError("名称不能为空。")
    parsed, remain = parse_datetime(tokens[index:], today, future_md=future_md)
    template = " ".join(remain).strip()
    return name, parsed, template


def parse_edit_args(tokens: list[str]) -> tuple[str, str, str]:
    if len(tokens) < 3:
        raise ParseError("用法：/倒计时 改 <序号或名称> 名称|日期|模板|开关 <值>")
    target = tokens[0]
    field = tokens[1]
    mapping = {
        "名称": "name",
        "名字": "name",
        "name": "name",
        "日期": "date",
        "时间": "date",
        "date": "date",
        "模板": "template",
        "句式": "template",
        "template": "template",
        "开关": "enabled",
        "enabled": "enabled",
    }
    key = mapping.get(field, mapping.get(field.lower(), ""))
    if not key:
        raise ParseError("可修改字段：名称、日期、模板、开关。")
    value = " ".join(tokens[2:]).strip()
    if not value:
        raise ParseError("缺少要修改的值。")
    return target, key, value


def parse_bool(text: str) -> bool:
    raw = text.strip().lower()
    if raw in {"1", "true", "yes", "on", "开", "开启", "启用"}:
        return True
    if raw in {"0", "false", "no", "off", "关", "关闭", "停用"}:
        return False
    raise ParseError("开关值应为 开 / 关。")


def resolve_timezone(name: str):
    try:
        return ZoneInfo((name or "").strip() or "Asia/Shanghai")
    except Exception:
        return timezone(timedelta(hours=8))
