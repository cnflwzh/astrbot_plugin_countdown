from datetime import date, datetime

import pytest

from countdown.parse import (
    ParseError,
    extract_after_command,
    parse_add_args,
    parse_clock,
    parse_command,
    parse_datetime,
    tokenize,
)


def test_extract_after_command():
    assert extract_after_command("/倒计时 添加 Dota3 2060-01-31") == "添加 Dota3 2060-01-31"
    assert extract_after_command("cd list") == "list"
    assert extract_after_command("/countdown") == ""
    assert extract_after_command("添加 Dota3 2060-01-31") == "添加 Dota3 2060-01-31"


def test_tokenize_quotes_and_book_title():
    assert tokenize('添加 "明日方舟：终末地" 2026-08-20 前瞻还有{days}天') == [
        "添加",
        "明日方舟：终末地",
        "2026-08-20",
        "前瞻还有{days}天",
    ]
    assert tokenize("添加 《Dota3》 2060-01-31 距离{name}还有{days}天") == [
        "添加",
        "《Dota3》",
        "2060-01-31",
        "距离{name}还有{days}天",
    ]


def test_parse_command_subcommands():
    parsed = parse_command("/倒计时 添加 《Dota3》 2060-01-31 距离{name}还有{days}天")
    assert parsed.sub == "add"
    assert parsed.tokens[0] == "《Dota3》"

    parsed = parse_command("/cd 正计时 开服 2024-06-01")
    assert parsed.sub == "countup"

    parsed = parse_command("/倒计时")
    assert parsed.sub == "help"

    with pytest.raises(ParseError):
        parse_command("/倒计时 乱写")


def test_parse_clock():
    assert parse_clock("9:00") == (9, 0)
    assert parse_clock("21:30") == (21, 30)
    with pytest.raises(ParseError):
        parse_clock("25:00")
    with pytest.raises(ParseError):
        parse_clock("abc")


def test_parse_datetime_formats():
    today = date(2026, 8, 18)
    parsed, remain = parse_datetime(["2060-01-31"], today, future_md=True)
    assert parsed.iso == "2060-01-31"
    assert parsed.has_time is False
    assert remain == []

    parsed, remain = parse_datetime(["2026年12月31日", "18:00", "extra"], today, future_md=True)
    assert parsed.iso == "2026-12-31T18:00:00"
    assert parsed.has_time is True
    assert remain == ["extra"]

    parsed, _ = parse_datetime(["1月1日"], today, future_md=True)
    assert parsed.value.date() == date(2027, 1, 1)

    parsed, _ = parse_datetime(["1月1日"], today, future_md=False)
    assert parsed.value.date() == date(2026, 1, 1)


def test_parse_add_args():
    today = date(2026, 8, 18)
    name, parsed, template = parse_add_args(
        ["《Dota3》", "2060-01-31", "距离{name}发售还有{days}天"],
        today,
        future_md=True,
    )
    assert name == "《Dota3》"
    assert parsed.value == datetime(2060, 1, 31)
    assert template == "距离{name}发售还有{days}天"

    with pytest.raises(ParseError):
        parse_add_args([], today, future_md=True)


def test_parse_add_name_then_glued_datetime():
    today = date(2026, 8, 18)
    parsed = parse_command("/倒计时 添加 《明日方舟：终末地》前瞻 2026年8月21日19:30")
    name, when, template = parse_add_args(parsed.tokens, today, future_md=True)
    assert name == "《明日方舟：终末地》前瞻"
    assert when.has_time is True
    assert when.value == datetime(2026, 8, 21, 19, 30)
    assert template == ""

    parsed, remain = parse_datetime(["2026年8月21日19:30"], today, future_md=True)
    assert parsed.has_time is True
    assert parsed.value == datetime(2026, 8, 21, 19, 30)
    assert remain == []


USER_ADD = "/倒计时 添加 《明日方舟：终末地》前瞻 2026年8月21日19:30"


def test_llm_tool_style_name_and_date_tokens():
    today = date(2026, 8, 18)
    tokens = tokenize("《明日方舟：终末地》前瞻 2026年8月21日19:30")
    name, when, template = parse_add_args(tokens, today, future_md=True)
    assert name == "《明日方舟：终末地》前瞻"
    assert when.value == datetime(2026, 8, 21, 19, 30)
    assert template == ""


def test_user_command_tokenize_splits_book_title_and_suffix():
    """《...》会被单独切出，后面的「前瞻」是下一个词，日期时刻粘在一起是第三个词。"""
    full = tokenize(USER_ADD.lstrip("/"))
    assert full == [
        "倒计时",
        "添加",
        "《明日方舟：终末地》",
        "前瞻",
        "2026年8月21日19:30",
    ]

    after_add = tokenize("《明日方舟：终末地》前瞻 2026年8月21日19:30")
    assert after_add == [
        "《明日方舟：终末地》",
        "前瞻",
        "2026年8月21日19:30",
    ]

    # 旧逻辑：第一个词当名称，第二个词当日期 -> 「前瞻」报错
    with pytest.raises(ParseError, match="前瞻"):
        parse_datetime(after_add[1:], date(2026, 8, 18), future_md=True)


def test_user_command_add_args_finds_date_after_name_suffix():
    today = date(2026, 8, 18)
    parsed = parse_command(USER_ADD)
    assert parsed.sub == "add"
    assert parsed.tokens == [
        "《明日方舟：终末地》",
        "前瞻",
        "2026年8月21日19:30",
    ]
    name, when, template = parse_add_args(parsed.tokens, today, future_md=True)
    assert name == "《明日方舟：终末地》前瞻"
    assert when.value == datetime(2026, 8, 21, 19, 30)
    assert when.has_time is True
    assert template == ""


@pytest.mark.parametrize(
    "raw",
    [
        USER_ADD,
        "倒计时 添加 《明日方舟：终末地》前瞻 2026年8月21日19:30",
        "添加 《明日方舟：终末地》前瞻 2026年8月21日19:30",
        "/倒计时 添加 《明日方舟：终末地》 前瞻 2026年8月21日 19:30",
    ],
)
def test_user_command_survives_astrbot_message_shapes(raw: str):
    today = date(2026, 8, 18)
    parsed = parse_command(raw)
    name, when, _template = parse_add_args(parsed.tokens, today, future_md=True)
    assert "明日方舟：终末地" in name
    assert "前瞻" in name
    assert when.value == datetime(2026, 8, 21, 19, 30)
    assert when.has_time is True
