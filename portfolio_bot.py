"""Interactive portfolio bot (long polling).

/start shows an inline-keyboard menu of projects from projects.json. Tapping a
project opens a card: description, optional photo, buttons linking to the live
demo / source code, and a Back button.

Run it wherever a process can stay up (your PC during a demo, or any free
worker host):

    python portfolio_bot.py

Security model: the bot only ever sends content from projects.json (a
whitelist you control). User input is never echoed back, callback data is
validated against known project ids, and all dynamic text is HTML-escaped.
"""

import json
import re
import sys
import time
from pathlib import Path

from config import load_dotenv, require
from tg import Bot, TelegramError, esc

PROJECTS_FILE = Path(__file__).with_name("projects.json")
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


# --- projects.json loading + validation ---------------------------------


def load_projects(path: Path = PROJECTS_FILE) -> dict[str, dict]:
    """Validate projects.json at startup so a typo fails loudly, not mid-demo."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"cannot read {path.name}: {e}")

    projects: dict[str, dict] = {}
    for i, item in enumerate(raw.get("projects", [])):
        pid = item.get("id", "")
        if not PROJECT_ID_RE.match(pid):
            raise SystemExit(f"projects[{i}]: id {pid!r} must match {PROJECT_ID_RE.pattern}")
        if pid in projects:
            raise SystemExit(f"projects[{i}]: duplicate id {pid!r}")
        for field in ("title", "description"):
            if not item.get(field, "").strip():
                raise SystemExit(f"projects[{i}] ({pid}): {field!r} is required")
        for field in ("image", "url", "repo"):
            link = item.get(field, "")
            if link and not link.startswith("https://"):
                raise SystemExit(f"projects[{i}] ({pid}): {field!r} must be an https:// URL")
        projects[pid] = item
    if not projects:
        raise SystemExit(f"{path.name} contains no projects")
    return projects


# --- rendering ----------------------------------------------------------


def menu_keyboard(projects: dict[str, dict]) -> dict:
    return {
        "inline_keyboard": [
            [{"text": p["title"], "callback_data": f"p:{pid}"}] for pid, p in projects.items()
        ]
    }


def project_keyboard(project: dict) -> dict:
    rows = []
    if project.get("url"):
        rows.append([{"text": "🌐 Open live demo", "url": project["url"]}])
    if project.get("repo"):
        rows.append([{"text": "📦 Source code", "url": project["repo"]}])
    rows.append([{"text": "⬅️ Back to menu", "callback_data": "menu"}])
    return {"inline_keyboard": rows}


def send_menu(bot: Bot, chat_id, projects: dict[str, dict]) -> None:
    bot.send_message(
        chat_id,
        "👋 <b>My portfolio</b>\nTap a project to see what it does:",
        reply_markup=menu_keyboard(projects),
    )


def send_project_card(bot: Bot, chat_id, project: dict) -> None:
    text = f"<b>{esc(project['title'])}</b>\n\n{esc(project['description'])}"
    keyboard = project_keyboard(project)
    if project.get("image"):
        try:
            bot.send_photo(chat_id, project["image"], caption=text, reply_markup=keyboard)
            return
        except TelegramError as e:
            # Bad/unreachable image URL shouldn't kill the demo — fall back to text.
            print(f"send_photo failed ({e}), falling back to text", file=sys.stderr)
    bot.send_message(chat_id, text, reply_markup=keyboard)


# --- update handling ----------------------------------------------------


def handle_message(bot: Bot, message: dict, projects: dict[str, dict]) -> None:
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    if chat_id is None or not isinstance(text, str):
        return  # ignore joins, photos, etc.
    command = text.split("@")[0].split()[0].lower() if text.strip() else ""
    if command in ("/start", "/projects", "/menu", "/help"):
        send_menu(bot, chat_id, projects)
    elif text.startswith("/"):
        bot.send_message(chat_id, "Unknown command — try /start")
    # Plain chat text is deliberately ignored (and never echoed back).


def handle_callback(bot: Bot, callback: dict, projects: dict[str, dict]) -> None:
    # Always answer, or the user's button shows a spinner for ~30s.
    bot.answer_callback_query(callback["id"])
    chat_id = callback.get("message", {}).get("chat", {}).get("id")
    if chat_id is None:
        return
    data = callback.get("data", "")
    if data == "menu":
        send_menu(bot, chat_id, projects)
    elif data.startswith("p:"):
        project = projects.get(data[2:])  # whitelist lookup — unknown ids are dropped
        if project:
            send_project_card(bot, chat_id, project)


def main() -> None:
    load_dotenv()
    bot = Bot(require("TG_TOKEN"))
    projects = load_projects()
    me = bot.call("getMe")
    print(f"@{me.get('username')} running with {len(projects)} project(s). Ctrl+C to stop.")

    offset = None
    while True:
        try:
            updates = bot.get_updates(offset)
        except TelegramError as e:
            if "409" in str(e):
                print("another process is polling this token — stop it first", file=sys.stderr)
            else:
                print(f"poll error: {e} — retrying in 5s", file=sys.stderr)
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                if "message" in update:
                    handle_message(bot, update["message"], projects)
                elif "callback_query" in update:
                    handle_callback(bot, update["callback_query"], projects)
            except TelegramError as e:
                # One failed send must not crash the loop for everyone else.
                print(f"handler error: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
