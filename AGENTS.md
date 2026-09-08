# AGENTS.md

This is an **AstrBot plugin**, not a standalone app. Entry point is `main.py`. License is AGPL-3.0 (`LICENSE`). Current platform target is **aiocqhttp only**.

User-facing usage lives in `README.md`. Keep this file for implementation rules and gotchas.

## Layout

| Path | Role |
| --- | --- |
| `main.py` | Plugin class, slash commands, LLM tools, ticker wiring |
| `countdown/` | Parse, store, render, card, permissions, schedule logic |
| `_conf_schema.json` | WebUI plugin config schema |
| `metadata.yaml` | Plugin id, version, author, platform, AstrBot range |
| `skills/countdown-manager/SKILL.md` | Agent skill: when/how to call `countdown_*` tools |
| `pack.py` | Build installable zip under `dist/` |
| `tests/` | Unit tests that must not import `astrbot` |

Keep `countdown` importable as a top-level package. `main.py` prepends the plugin dir to `sys.path` and **evicts cached `countdown.*` modules** before import, because AstrBot reloads plugins in-process.

## Data paths (official)

Do **not** invent `plugins_data`. Official names:

| What | Path |
| --- | --- |
| Plugin code | `data/plugins/astrbot_plugin_countdown/` |
| WebUI config | `data/config/astrbot_plugin_countdown_config.json` |
| Task JSON + cards | `data/plugin_data/astrbot_plugin_countdown/` via `StarTools.get_data_dir("astrbot_plugin_countdown")` |
| Skill copy for sandbox | `data/skills/countdown-manager/SKILL.md` (copied on `initialize`) |

Never persist user tasks inside the plugin install directory. Updates overwrite that tree.

## Commands and tools

Slash group: `/倒计时` (`/cd`, `/countdown`). Subcommands: add, countup, list, query, delete, edit, toggle, time, enable, disable, help.

LLM tools (same session, same permissions): `countdown_add`, `countdown_list`, `countdown_query`, `countdown_edit`, `countdown_delete`.

Group isolation key is `{platform_id}:GroupMessage:{group_id}`. Do not use `event.unified_msg_origin` as the store key when unique_session is on.

## Parse rules

- `《书名号》` is one token; text glued after `》` (e.g. `前瞻`) is **name**, not date.
- Find the first date-like token; everything before it is the name.
- Accept glued datetimes: `2026年8月21日19:30`.
- Add a unit test for any new natural-language date/name shape before changing `countdown/parse.py`.

## Timed tasks

Date-only countdown: event-day template `{name}就在今天！`, then delete after daily broadcast.

Timed countdown:

1. Daily card still uses remaining time (`{remain}`).
2. Pre-remind ~10 minutes before target.
3. Due remind at target (`{name}到时间了！`).
4. Delete only **after** due remind succeeds (`due_reminded`).

Tick order: pre-remind → due-remind → cleanup → daily broadcast.

## Style and tests

- Python 3.10+, ruff (`ruff.toml`): quotes double, line length 100. `main.py` may violate E402 because of the `sys.path` bootstrap.
- Format with ruff before finishing a change.
- `python -m pytest tests` must pass. Core parse/render/store tests must not import AstrBot.
- `tests/test_card.py` needs Pillow.
- Do not use `requests`; this plugin should not need network I/O.

## Pack and install

```bash
python pack.py
```

Zip root **must** be `astrbot_plugin_countdown/` (needed for WebUI upload). Bump `metadata.yaml` and `@register(..., version)` together.

WebUI overlay install does **not** delete removed files and may keep old `countdown/*.py` plus in-memory modules. If load fails with `cannot import name ...`, uninstall, delete `data/plugins/astrbot_plugin_countdown`, reinstall. Prefer adding new symbols with import fallbacks when extending existing modules.

Sandbox agents may try to `cat /workspace/skills/countdown-manager/SKILL.md`. Plugin skills often are **not** in the sandbox workspace; the `countdown_*` tools still work. Skill copy on startup is for Shipyard scan. Skill text must tell the model to **call tools**, not read SKILL.md from disk.

## Releases

```bash
python pack.py
# gh may need GH_TOKEN/GITHUB_TOKEN unset if they override a valid keyring login
gh release create vX.Y.Z dist/astrbot_plugin_countdown-vX.Y.Z.zip --title "vX.Y.Z" --notes-file notes.md
```

Do not commit `dist/`.
