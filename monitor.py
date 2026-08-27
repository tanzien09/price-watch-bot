"""Scheduled monitor: fetch a number from a public JSON API, alert on Telegram.

Runs stateless on GitHub Actions cron; last seen value persists in state.json,
which the workflow commits back to the repo.

Usage:
    python monitor.py          # one monitoring run
    python monitor.py --test   # just send "bot is alive" to verify credentials
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import get, load_dotenv, require, require_float
from tg import Bot, TelegramError, esc

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
USER_AGENT = "price-watch-bot (portfolio project; low-frequency polling)"

# Defaults let the bot run with zero target config: BTC price in USD from
# CoinGecko's free, keyless API (endpoint verified working 2026-08-27).
DEFAULT_TARGET_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
DEFAULT_JSON_PATH = "bitcoin.usd"
DEFAULT_TARGET_NAME = "Bitcoin price (USD)"

ALERT_MODES = ("change", "threshold_above", "threshold_below", "report")


# --- fetch + parse ------------------------------------------------------


def fetch_json(url: str) -> dict | list:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def extract_value(data, json_path: str) -> float:
    """Walk a dot-separated path ('bitcoin.usd', 'rates.0.value') into JSON."""
    current = data
    for segment in json_path.split("."):
        if isinstance(current, list):
            if not segment.isdigit() or int(segment) >= len(current):
                raise ValueError(f"bad list index {segment!r} in JSON_PATH {json_path!r}")
            current = current[int(segment)]
        elif isinstance(current, dict):
            if segment not in current:
                raise ValueError(f"key {segment!r} not found in response (JSON_PATH {json_path!r})")
            current = current[segment]
        else:
            raise ValueError(f"cannot descend into {type(current).__name__} at {segment!r}")
    try:
        return float(current)
    except (TypeError, ValueError):
        raise ValueError(f"value at {json_path!r} is not a number: {current!r}") from None


# --- alert decision -----------------------------------------------------


def should_alert(mode: str, value: float, last: float | None, threshold: float | None) -> bool:
    """First run (last is None) always alerts, as a baseline message.

    Threshold modes alert only when the value CROSSES the threshold, so a
    30-minute cron doesn't spam the same alert while the value sits past it.
    """
    if mode == "report":
        return True
    if last is None:
        return True
    if mode == "change":
        return value != last
    if mode == "threshold_above":
        return value >= threshold and last < threshold
    if mode == "threshold_below":
        return value <= threshold and last > threshold
    raise ValueError(f"unknown ALERT_MODE {mode!r}")


def compose_message(name: str, value: float, last: float | None, url: str) -> str:
    lines = [f"📊 <b>{esc(name)}</b>", f"Current: <b>{value:,.6g}</b>"]
    if last is not None and last != 0:
        delta = value - last
        arrow = "🔺" if delta > 0 else ("🔻" if delta < 0 else "➡️")
        lines.append(f"{arrow} vs last run: {delta:+,.6g} ({delta / last:+.2%})")
    lines.append(f"🕒 {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    lines.append(f'🔗 <a href="{esc(url)}">source</a>')
    return "\n".join(lines)


# --- state --------------------------------------------------------------


def read_state() -> float | None:
    if not STATE_FILE.is_file():
        return None
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))["last_value"]
        return float(value)
    except (ValueError, KeyError, TypeError):
        print(f"warning: {STATE_FILE} is corrupt, treating as first run", file=sys.stderr)
        return None


def write_state(value: float) -> None:
    # Atomic write: never leave a half-written state.json if the run dies.
    tmp = STATE_FILE.with_suffix(".tmp")
    payload = {"last_value": value, "updated_at": datetime.now(timezone.utc).isoformat()}
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATE_FILE)


# --- main ---------------------------------------------------------------


def run(bot: Bot, chat_id: str) -> None:
    url = get("TARGET_URL", DEFAULT_TARGET_URL)
    if not url.startswith(("http://", "https://")):
        raise SystemExit(f"TARGET_URL must be an http(s) URL, got {url!r}")
    json_path = get("JSON_PATH", DEFAULT_JSON_PATH)
    name = get("TARGET_NAME", DEFAULT_TARGET_NAME)
    mode = get("ALERT_MODE", "change").lower()
    if mode not in ALERT_MODES:
        raise SystemExit(f"ALERT_MODE must be one of {ALERT_MODES}, got {mode!r}")
    threshold = require_float("THRESHOLD") if mode.startswith("threshold") else None

    value = extract_value(fetch_json(url), json_path)
    last = read_state()
    print(f"{name}: current={value} last={last} mode={mode}")

    if should_alert(mode, value, last, threshold):
        bot.send_message(chat_id, compose_message(name, value, last, url))
        print("alert sent")
    else:
        print("no alert needed")
    write_state(value)


def main() -> None:
    load_dotenv()
    bot = Bot(require("TG_TOKEN"))
    chat_id = require("TG_CHAT_ID")

    if "--test" in sys.argv:
        bot.send_message(chat_id, "✅ bot is alive — credentials work")
        print("test message sent")
        return

    try:
        run(bot, chat_id)
    except (requests.RequestException, ValueError, TelegramError) as e:
        # Report the failure to Telegram instead of dying silently, then exit
        # non-zero so the Actions run still shows red.
        error_chat = get("TG_ADMIN_CHAT_ID") or chat_id
        try:
            bot.send_message(error_chat, f"⚠️ <b>monitor failed</b>\n<code>{esc(e)}</code>")
        except TelegramError as report_error:
            print(f"could not report error to Telegram: {report_error}", file=sys.stderr)
        raise SystemExit(f"monitor failed: {e}")


if __name__ == "__main__":
    main()
