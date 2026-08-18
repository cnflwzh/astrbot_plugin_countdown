from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import datetime
from pathlib import Path

_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

# AstrBot reloads plugins in the same process. Drop cached submodules so a
# newly extracted countdown/*.py is imported instead of the previous version.
for _mod in list(sys.modules):
    if _mod == "countdown" or _mod.startswith("countdown."):
        del sys.modules[_mod]

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

from countdown.logic import (
    clock_label,
    expired_countdowns,
    find_task,
    name_exists,
    should_broadcast,
    should_pre_remind,
    tasks_for_broadcast,
)

try:
    from countdown.logic import should_due_remind
except ImportError:

    def should_due_remind(task, now):
        if not getattr(task, "enabled", True) or getattr(task, "mode", "") != "countdown":
            return False
        if not getattr(task, "has_time", False) or getattr(task, "due_reminded", False):
            return False
        return now >= task.target_datetime()
from countdown.models import Task
from countdown.parse import (
    ParseError,
    format_clock,
    parse_add_args,
    parse_bool,
    parse_clock,
    parse_command,
    parse_datetime,
    parse_edit_args,
    resolve_timezone,
)
from countdown.perms import can_manage, can_query
from countdown.render import (
    build_render_items,
    header_context,
    preserve_newlines,
    render_template,
    task_context,
    task_delta_days,
)
from countdown.session import (
    group_id,
    is_group_message,
    platform_id,
    platform_name,
    sender_id,
    session_key,
    session_umo,
)
from countdown.store import JsonStore
from countdown.ticker import DailyTicker

HELP_TEXT = """【倒计时】每个群的任务互相隔离

添加
  /倒计时 添加 <名称> <日期> [模板]
  /倒计时 添加 《Dota3》 2060-01-31 距离《{name}》发售还有{days}天
  /倒计时 添加 《明日方舟：终末地》前瞻 2026年8月21日19:30
  /倒计时 正计时 <名称> <日期> [模板]
  /倒计时 正计时 开服 2024-06-01 {name}已经过去{days}天

管理
  /倒计时 列表
  /倒计时 查询
  /倒计时 删除 <序号或名称>
  /倒计时 改 <序号或名称> 名称|日期|模板|开关 <值>
  /倒计时 时间 [HH:MM]
  /倒计时 开启 / 关闭
  /倒计时 帮助

日期支持 2026-12-31、2026年12月31日、12月31日，也可写成 2026-12-31 18:00 或 2026年8月21日19:30。
名称可用引号或《书名号》，书名号后面的说明会算进名称。

标题占位符：{year} {month} {day} {weekday} {today} {today_iso}
条目占位符：{name} {days} {hours} {minutes} {remain} {target} {target_time} {mode}
仅写日期的任务到期当天改成「{name}就在今天！」。带时刻的任务会按剩余时间播报，正点前 10 分钟提醒一次，到点再提醒一次。"""


def _data_dir() -> Path:
    try:
        from astrbot.api.star import StarTools

        return Path(str(StarTools.get_data_dir("astrbot_plugin_countdown")))
    except Exception:
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            return Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_countdown"
        except Exception:
            return Path("data") / "plugin_data" / "astrbot_plugin_countdown"


@register(
    "astrbot_plugin_countdown",
    "cnflwzh",
    "按群隔离的倒计时 / 正计时，支持模板占位符和每日定时播报",
    "1.3.3",
)
class CountdownPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.store = JsonStore(_data_dir() / "data.json")
        self.store.load()
        self._ticker = DailyTicker(self._on_tick)
        self._broadcast_lock = asyncio.Lock()

    async def initialize(self):
        self.store.load()
        self._ticker.start()
        logger.info("astrbot_plugin_countdown initialized")

    async def terminate(self):
        await self._ticker.stop()
        self.store.save()
        logger.info("astrbot_plugin_countdown terminated")

    def _cfg(self, key: str, default=None):
        try:
            value = self.config.get(key, default)
        except Exception:
            return default
        return default if value is None else value

    def _now(self) -> datetime:
        tz = resolve_timezone(str(self._cfg("timezone", "Asia/Shanghai") or "Asia/Shanghai"))
        return datetime.now(tz).replace(tzinfo=None)

    def _templates(self) -> dict[str, str]:
        return {
            "header_template": str(
                self._cfg("header_template", "今天是{year}年{month}月{day}日。") or ""
            ),
            "countdown_template": str(
                self._cfg("countdown_item_template", "距离{name}还有{days}天") or ""
            ),
            "countup_template": str(
                self._cfg("countup_item_template", "{name}已经过去{days}天") or ""
            ),
            "today_template": str(self._cfg("today_item_template", "{name}就在今天！") or ""),
            "countdown_time_template": str(
                self._cfg("countdown_time_template", "距离{name}还有{remain}") or ""
            ),
            "item_prefix": str(self._cfg("item_prefix", "- ") or ""),
        }

    def _require_session(self, event: AstrMessageEvent):
        if platform_name(event) != "aiocqhttp":
            raise ParseError("当前版本仅支持 aiocqhttp（OneBot v11）。")
        if not is_group_message(event) and not bool(self._cfg("allow_private", True)):
            raise ParseError("当前未开启私聊使用。可在插件配置中打开「允许私聊使用」。")
        return self.store.ensure_session(
            session_key(event),
            umo=session_umo(event),
            platform_id=platform_id(event),
            group_id=group_id(event),
            is_group=is_group_message(event),
        )

    def _assert_manage(self, event: AstrMessageEvent) -> None:
        if can_manage(
            event,
            context=self.context,
            mode=str(self._cfg("manage_permission", "astrbot_admin")),
            plugin_admin_ids=self._cfg("plugin_admin_ids", []) or [],
        ):
            return
        raise ParseError(
            "只有管理员可以执行该操作。请在仪表盘「配置 -> 其他配置 -> 管理员 ID」中添加，"
            "或在本插件配置里调整权限模式 / 额外管理员。"
        )

    def _assert_query(self, event: AstrMessageEvent) -> None:
        if can_query(
            event,
            context=self.context,
            allow_all=bool(self._cfg("allow_query_all", True)),
            mode=str(self._cfg("manage_permission", "astrbot_admin")),
            plugin_admin_ids=self._cfg("plugin_admin_ids", []) or [],
        ):
            return
        raise ParseError("只有管理员可以查询倒计时。")

    def _payload(self, tasks: list[Task], now: datetime):
        kwargs = self._templates()
        try:
            accepted = set(inspect.signature(build_render_items).parameters)
            kwargs = {key: value for key, value in kwargs.items() if key in accepted}
        except (TypeError, ValueError):
            kwargs.pop("countdown_time_template", None)
        return build_render_items(tasks, now, **kwargs)

    def _render(self, tasks: list[Task], now: datetime) -> str:
        return self._payload(tasks, now)[1]

    def _render_card(self, key: str, now: datetime, items) -> Path | None:
        if not bool(self._cfg("send_image", True)):
            return None
        try:
            from countdown.card import render_card

            ctx = header_context(now)
            safe = "".join(ch if ch.isalnum() else "_" for ch in key)[:80] or "session"
            path = _data_dir() / "cards" / f"{safe}.png"
            return render_card(
                path,
                header=str(ctx.get("today") or ""),
                weekday=str(ctx.get("weekday") or ""),
                items=items,
            )
        except Exception:
            logger.exception("failed to render countdown card")
            return None

    def _reply(self, event: AstrMessageEvent, text: str):
        return event.plain_result(preserve_newlines(text))

    def _build_chain(
        self, text: str, *, at_all: bool = False, image: Path | None = None
    ) -> MessageChain:
        parts = []
        if at_all:
            parts.append(Comp.At(qq="all"))
        if image is not None:
            parts.append(Comp.Image.fromFileSystem(str(image)))
        else:
            parts.append(Comp.Plain(preserve_newlines(text)))
        chain = MessageChain()
        chain.chain = parts
        return chain

    @filter.command("倒计时", alias={"cd", "countdown"})
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def countdown_cmd(self, event: AstrMessageEvent, message: str = ""):
        """按群隔离的倒计时 / 正计时。发送 /倒计时 帮助 查看用法。"""
        try:
            raw = (event.message_str or "").strip()
            extra = (message or "").strip()
            if extra and extra not in raw:
                raw = f"{raw} {extra}".strip()
            parsed = parse_command(raw)
            handler = {
                "add": self._cmd_add,
                "countup": self._cmd_countup,
                "list": self._cmd_list,
                "delete": self._cmd_delete,
                "edit": self._cmd_edit,
                "query": self._cmd_query,
                "time": self._cmd_time,
                "toggle": self._cmd_toggle,
                "enable": self._cmd_enable,
                "disable": self._cmd_disable,
                "help": self._cmd_help,
            }[parsed.sub]
            async for result in handler(event, parsed.tokens):
                yield result
        except ParseError as exc:
            yield self._reply(event, str(exc))
        except Exception:
            logger.exception("countdown command failed")
            yield self._reply(event, "处理指令时出错，请查看日志。")

    async def _cmd_help(self, event: AstrMessageEvent, _tokens: list[str]):
        yield self._reply(event, HELP_TEXT)

    async def _cmd_add(self, event: AstrMessageEvent, tokens: list[str]):
        self._assert_manage(event)
        async for result in self._add_task(event, tokens, mode="countdown"):
            yield result

    async def _cmd_countup(self, event: AstrMessageEvent, tokens: list[str]):
        self._assert_manage(event)
        async for result in self._add_task(event, tokens, mode="countup"):
            yield result

    async def _add_task(self, event: AstrMessageEvent, tokens: list[str], *, mode: str):
        session = self._require_session(event)
        now = self._now()
        name, parsed_date, template = parse_add_args(
            tokens,
            now.date(),
            future_md=(mode == "countdown"),
        )
        if len(name) > 50:
            raise ParseError("名称过长，最多 50 个字符。")
        if len(template) > 200:
            raise ParseError("模板过长，最多 200 个字符。")
        days = (parsed_date.value.date() - now.date()).days
        if mode == "countdown":
            if parsed_date.has_time and parsed_date.value <= now:
                raise ParseError("倒计时的目标时间不能早于现在。")
            if not parsed_date.has_time and days < 0:
                raise ParseError("倒计时的目标日期不能早于今天。")
        if mode == "countup" and days > 0:
            raise ParseError("正计时的起始日期不能晚于今天。")
        if name_exists(session, name):
            raise ParseError(f"本群已存在同名任务「{name}」。")
        limit = int(self._cfg("max_tasks_per_group", 30) or 30)
        if len(session.tasks) >= limit:
            raise ParseError(f"本群任务数已达上限（{limit}）。")
        task = Task(
            id=self.store.next_id(session),
            name=name,
            mode=mode,  # type: ignore[arg-type]
            target=parsed_date.iso,
            template=template,
            created_by=sender_id(event),
            created_at=now.isoformat(timespec="seconds"),
            has_time=parsed_date.has_time,
        )
        self.store.add_task(session, task)
        preview = self._render([task], now)
        kind = "倒计时" if mode == "countdown" else "正计时"
        extra = ""
        if mode == "countdown" and parsed_date.has_time:
            minutes = int(self._cfg("pre_remind_minutes", 10) or 10)
            extra = (
                f"\n将在 {parsed_date.value.strftime('%H:%M')} 前 {minutes} 分钟提醒一次，"
                "到点再提醒一次。"
            )
        yield self._reply(event, f"已添加{kind}任务：\n{preview}{extra}")

    async def _cmd_list(self, event: AstrMessageEvent, _tokens: list[str]):
        self._assert_query(event)
        session = self._require_session(event)
        now = self._now()
        if not session.tasks:
            yield self._reply(event, "本群还没有倒计时或正计时任务。")
            return
        default_time = str(self._cfg("broadcast_time", "09:00") or "09:00")
        status = "已开启" if session.broadcast_enabled else "已关闭"
        lines = [
            f"本群共 {len(session.tasks)} 个任务，每日 {clock_label(session, default_time)} 播报（{status}）",
            "",
        ]
        for index, task in enumerate(session.tasks, start=1):
            days = task_delta_days(task, now)
            kind = "倒计时" if task.mode == "countdown" else "正计时"
            paused = "（已停用）" if not task.enabled else ""
            if task.mode == "countdown":
                remain = str(task_context(task, now).get("remain") or "").strip()
                extra = f"还有 {remain}" if remain else f"还有 {max(0, days)} 天"
            else:
                extra = f"已过 {max(0, days)} 天"
            when = task.target_date().isoformat()
            if task.has_time:
                when = f"{when} {task.target_datetime().strftime('%H:%M')}"
            lines.append(f"{index}. [{kind}] {task.name} → {when} {extra}{paused}")
        yield self._reply(event, "\n".join(lines))

    async def _cmd_delete(self, event: AstrMessageEvent, tokens: list[str]):
        self._assert_manage(event)
        if not tokens:
            raise ParseError("用法：/倒计时 删除 <序号或名称>")
        session = self._require_session(event)
        task = find_task(session, " ".join(tokens))
        if task is None:
            raise ParseError("没有找到对应任务，先用 /倒计时 列表 查看序号。")
        self.store.remove_task(session, task)
        yield self._reply(event, f"已删除任务「{task.name}」。")

    async def _cmd_edit(self, event: AstrMessageEvent, tokens: list[str]):
        self._assert_manage(event)
        target, field, value = parse_edit_args(tokens)
        session = self._require_session(event)
        task = find_task(session, target)
        if task is None:
            raise ParseError("没有找到对应任务，先用 /倒计时 列表 查看序号。")
        now = self._now()

        def apply():
            if field == "name":
                name = value.strip()
                if not name:
                    raise ParseError("名称不能为空。")
                if len(name) > 50:
                    raise ParseError("名称过长，最多 50 个字符。")
                if name_exists(session, name, exclude_id=task.id):
                    raise ParseError(f"本群已存在同名任务「{name}」。")
                task.name = name
                return
            if field == "template":
                if len(value) > 200:
                    raise ParseError("模板过长，最多 200 个字符。")
                task.template = value
                return
            if field == "enabled":
                task.enabled = parse_bool(value)
                return
            parsed_date, extra = parse_datetime(
                value.split(),
                now.date(),
                future_md=(task.mode == "countdown"),
            )
            if extra:
                raise ParseError("日期格式不正确。")
            days = (parsed_date.value.date() - now.date()).days
            if task.mode == "countdown":
                if parsed_date.has_time and parsed_date.value <= now:
                    raise ParseError("倒计时的目标时间不能早于现在。")
                if not parsed_date.has_time and days < 0:
                    raise ParseError("倒计时的目标日期不能早于今天。")
            if task.mode == "countup" and days > 0:
                raise ParseError("正计时的起始日期不能晚于今天。")
            task.target = parsed_date.iso
            task.has_time = parsed_date.has_time
            task.pre_reminded = False
            task.due_reminded = False

        self.store.mutate(apply)
        yield self._reply(event, f"已更新任务「{task.name}」。\n{self._render([task], now)}")

    async def _cmd_query(self, event: AstrMessageEvent, _tokens: list[str]):
        self._assert_query(event)
        session = self._require_session(event)
        now = self._now()
        tasks = [
            task
            for task in session.enabled_tasks()
            if not (task.mode == "countdown" and task_delta_days(task, now) < 0)
        ]
        if not tasks:
            yield self._reply(event, "本群当前没有可播报的任务。")
            return
        _header, text, items = self._payload(tasks, now)
        image = self._render_card(session.key, now, items)
        if image is not None:
            yield event.image_result(str(image))
            return
        yield self._reply(event, text)

    async def _cmd_time(self, event: AstrMessageEvent, tokens: list[str]):
        session = self._require_session(event)
        default_time = str(self._cfg("broadcast_time", "09:00") or "09:00")
        if not tokens:
            source = "本群自定义" if session.broadcast_time else "插件默认"
            yield self._reply(
                event,
                f"本群每日播报时间：{clock_label(session, default_time)}（{source}）\n"
                "管理员可用 /倒计时 时间 21:30 修改，或发送 /倒计时 时间 默认 恢复。",
            )
            return
        self._assert_manage(event)
        raw = tokens[0]
        if raw in {"默认", "default", "reset"}:

            def reset():
                session.broadcast_time = None

            self.store.mutate(reset)
            yield self._reply(event, f"已恢复为插件默认播报时间 {default_time}。")
            return
        hour, minute = parse_clock(raw)
        clock = format_clock(hour, minute)

        def apply():
            session.broadcast_time = clock

        self.store.mutate(apply)
        yield self._reply(event, f"已将本群每日播报时间设为 {clock}。")

    async def _cmd_toggle(self, event: AstrMessageEvent, tokens: list[str]):
        self._assert_manage(event)
        if not tokens:
            raise ParseError("用法：/倒计时 开关 <序号或名称>")
        session = self._require_session(event)
        task = find_task(session, " ".join(tokens))
        if task is None:
            raise ParseError("没有找到对应任务。")

        def apply():
            task.enabled = not task.enabled

        self.store.mutate(apply)
        state = "启用" if task.enabled else "停用"
        yield self._reply(event, f"已{state}任务「{task.name}」。")

    async def _cmd_enable(self, event: AstrMessageEvent, _tokens: list[str]):
        self._assert_manage(event)
        session = self._require_session(event)

        def apply():
            session.broadcast_enabled = True

        self.store.mutate(apply)
        yield self._reply(event, "已开启本群每日播报。")

    async def _cmd_disable(self, event: AstrMessageEvent, _tokens: list[str]):
        self._assert_manage(event)
        session = self._require_session(event)

        def apply():
            session.broadcast_enabled = False

        self.store.mutate(apply)
        yield self._reply(event, "已关闭本群每日播报。任务仍保留，可用 /倒计时 查询 手动查看。")

    async def _on_tick(self, _wall: datetime) -> None:
        try:
            now = self._now()
            default_time = str(self._cfg("broadcast_time", "09:00") or "09:00")
            catch_up = int(self._cfg("catch_up_minutes", 10) or 0)
            cleanup = bool(self._cfg("cleanup_after_zero", True))
            async with self._broadcast_lock:
                for session in self.store.iter_sessions():
                    await self._send_pre_reminds(session, now)
                    await self._send_due_reminds(session, now)
                self._cleanup_overdue(now, cleanup)
                for session in self.store.iter_sessions():
                    if not should_broadcast(
                        session,
                        now,
                        default_time=default_time,
                        catch_up_minutes=catch_up,
                    ):
                        continue
                    await self._broadcast_session(session, now, cleanup=cleanup)
        except Exception:
            logger.exception("countdown tick failed")

    def _cleanup_overdue(self, now: datetime, cleanup: bool) -> None:
        changed = False
        for session in self.store.iter_sessions():
            overdue = expired_countdowns(
                session, now, cleanup_after_zero=cleanup, include_zero=False
            )
            if not overdue:
                continue
            ids = {task.id for task in overdue}
            session.tasks = [task for task in session.tasks if task.id not in ids]
            changed = True
            logger.info("cleaned %s overdue countdown(s) in %s", len(overdue), session.key)
        if changed:
            self.store.save()

    async def _send_pre_reminds(self, session, now: datetime) -> None:
        minutes = int(self._cfg("pre_remind_minutes", 10) or 10)
        template = str(self._cfg("pre_remind_template", "{name}还有{minutes}分钟！") or "")
        pending = [task for task in session.tasks if should_pre_remind(task, now, minutes=minutes)]
        if not pending:
            return
        sent_ids: list[str] = []
        for task in pending:
            ctx = task_context(task, now)
            ctx["minutes"] = minutes
            text = render_template(template, ctx)
            try:
                result = await self.context.send_message(session.umo, self._build_chain(text))
            except Exception:
                logger.exception("failed to send pre-remind for %s", task.name)
                continue
            if result is False:
                logger.warning("pre-remind send_message returned False for %s", session.umo)
                continue
            sent_ids.append(task.id)
        if not sent_ids:
            return

        def mark():
            for task in session.tasks:
                if task.id in sent_ids:
                    task.pre_reminded = True

        self.store.mutate(mark)

    async def _send_due_reminds(self, session, now: datetime) -> None:
        template = str(self._cfg("due_remind_template", "{name}到时间了！") or "")
        pending = [task for task in session.tasks if should_due_remind(task, now)]
        if not pending:
            return
        sent_ids: list[str] = []
        for task in pending:
            ctx = task_context(task, now)
            text = render_template(template, ctx)
            try:
                result = await self.context.send_message(session.umo, self._build_chain(text))
            except Exception:
                logger.exception("failed to send due remind for %s", task.name)
                continue
            if result is False:
                logger.warning("due-remind send_message returned False for %s", session.umo)
                continue
            sent_ids.append(task.id)
        if not sent_ids:
            return

        def mark():
            for task in session.tasks:
                if task.id in sent_ids:
                    task.due_reminded = True

        self.store.mutate(mark)

    async def _broadcast_session(self, session, now: datetime, *, cleanup: bool) -> None:
        tasks = tasks_for_broadcast(session, now)
        if not tasks:
            return
        _header, text, items = self._payload(tasks, now)
        image = self._render_card(session.key, now, items)
        at_all = bool(self._cfg("at_all_on_zero", False)) and any(
            task.mode == "countdown" and task_delta_days(task, now) <= 0 for task in tasks
        )
        try:
            result = await self.context.send_message(
                session.umo, self._build_chain(text, at_all=at_all, image=image)
            )
        except Exception:
            logger.exception("failed to broadcast countdown to %s", session.umo)
            return
        if result is False:
            logger.warning("send_message returned False for %s", session.umo)
            return
        today = now.date().isoformat()

        def apply():
            session.last_broadcast_date = today
            if cleanup:
                finished = expired_countdowns(
                    session, now, cleanup_after_zero=True, include_zero=True
                )
                if finished:
                    ids = {task.id for task in finished}
                    session.tasks = [task for task in session.tasks if task.id not in ids]
                    logger.info(
                        "removed %s finished countdown(s) in %s", len(finished), session.key
                    )

        self.store.mutate(apply)
