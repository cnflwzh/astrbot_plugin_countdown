---
name: countdown-manager
description: 管理当前群的倒计时和正计时。用户要加/改/删/查倒计时、发售日、还有几天时，直接调用 countdown_add、countdown_list、countdown_query、countdown_edit、countdown_delete。不要用 shell 或读文件去打开 SKILL.md。
---

# 倒计时

工具已经注册在当前对话里。直接调用，不要 `cat`、不要读 `/workspace/skills/`。

只操作当前会话。日期用用户原话，不要编造。

## 工具

- `countdown_add`：添加。`mode` 为 `countdown`（默认）或 `countup`。正计时日期必须是今天或更早。
- `countdown_list`：看序号、名称、日期和剩余时间。改/删前先列出。
- `countdown_query`：给用户发卡片并返回文字摘要。
- `countdown_edit`：改已有任务。`field` 只能是 `name`、`date`、`template`、`enabled`。
- `countdown_delete`：按序号或准确名称删除。

## 规则

1. 名称含糊时先 `countdown_list`，确认序号再改或删。
2. 日期写成 `2026-08-21`、`2026年8月21日` 或 `2026年8月21日19:30`。
3. 工具成功后只做一句确认，不要再复述完整列表。
4. 没有权限或日期无效时，把工具返回的错误原样告诉用户。
