"""Minimal Telegram Bot API client — requests only, no framework.

Security notes:
- The bot token never appears in exception messages. requests' own exceptions
  embed the full URL (which contains the token), so network errors are caught
  and re-raised sanitized before they can reach logs.
- All dynamic text sent with parse_mode=HTML must go through esc() first.
"""

import html

import requests

# Telegram hard limit (https://core.telegram.org/bots/api)
MAX_MESSAGE_LEN = 4096


class TelegramError(RuntimeError):
    """A Telegram API call failed. Message is safe to log (no token)."""


def esc(text: str) -> str:
    """Escape text for parse_mode=HTML messages."""
    return html.escape(str(text), quote=False)


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Bot:
    def __init__(self, token: str, timeout: int = 15):
        # Fail fast on obviously bad tokens instead of confusing 404s later.
        if not token or ":" not in token:
            raise SystemExit(
                "TG_TOKEN looks invalid — expected the '<id>:<secret>' string from @BotFather."
            )
        self._base = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout
        # One session = connection reuse across calls (faster, fewer handshakes).
        self._session = requests.Session()

    def call(self, method: str, timeout: int | None = None, **params):
        try:
            resp = self._session.post(
                f"{self._base}/{method}", json=params, timeout=timeout or self._timeout
            )
        except requests.RequestException as e:
            # Do NOT propagate e: its message can contain the token URL.
            raise TelegramError(f"{method}: network error ({type(e).__name__})") from None
        try:
            data = resp.json()
        except ValueError:
            raise TelegramError(f"{method}: non-JSON response (HTTP {resp.status_code})") from None
        if not data.get("ok"):
            raise TelegramError(
                f"{method}: {data.get('description', 'unknown error')} (HTTP {resp.status_code})"
            )
        return data.get("result")

    def send_message(self, chat_id, text: str):
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=truncate(text, MAX_MESSAGE_LEN),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
