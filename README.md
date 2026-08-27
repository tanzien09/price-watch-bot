# Price Watch Bot + Portfolio Menu

A Python Telegram bot with two jobs, sharing one codebase and one bot token:

1. **Monitor (automated):** polls a public JSON API on a GitHub Actions cron
   (default: Bitcoin/USD from CoinGecko), detects changes or threshold
   crossings, and alerts a Telegram channel. Fetch errors are reported to
   Telegram instead of failing silently. Runs **free, no server needed**.
2. **Portfolio menu (interactive):** message the bot `/start` and it shows an
   inline-button menu of my projects — tap one for a description + screenshot
   and buttons to the live demo and source code.

> 📸 *Add a screenshot/GIF of the Telegram alert + menu here before publishing.*

**Architecture:** GitHub Actions cron → `monitor.py` → target API → Telegram
channel · `state.json` committed back between runs · `portfolio_bot.py` long-polls
the same token for the interactive menu.

**Stack:** Python 3.11+ · `requests` (only runtime dependency) · Telegram Bot
API · GitHub Actions · pytest.

This bot also delivers the lead notifications for my
[lead-funnel project](https://github.com/CHANGE-ME/lead-funnel) — the two work
as one system.

## Quick start (one command)

Prereqs: Python 3.11+, a bot token from [@BotFather](https://t.me/BotFather)
(`/newbot`), and a group/channel with the bot added as admin.

```powershell
# Windows
.\setup.ps1            # venv + deps + credentials + tests + live smoke test
.\setup.ps1 -Deploy    # all of the above + create GitHub repo + set Actions secrets (needs gh CLI)
```

```bash
# Linux / macOS
./setup.sh             # same; add --deploy to also push to GitHub
```

The script ends with a **"bot is alive"** message in your Telegram and a first
real monitor run. After `-Deploy`, the cron is live: the repo's **Actions →
monitor → Run workflow** button triggers it on demand (that's the demo button).

## Configure what it watches

Everything is environment variables — locally in `.env` (git-ignored, see
[.env.example](.env.example)), on GitHub under **Settings → Secrets and
variables → Actions** (secrets: `TG_TOKEN`, `TG_CHAT_ID`; the rest as
*Variables*).

| Variable | Default | Meaning |
|---|---|---|
| `TG_TOKEN` | — (required) | Bot token from @BotFather |
| `TG_CHAT_ID` | — (required) | Chat/channel that receives alerts |
| `TG_ADMIN_CHAT_ID` | `TG_CHAT_ID` | Where error reports go |
| `TARGET_URL` | CoinGecko BTC/USD | Any public JSON API |
| `JSON_PATH` | `bitcoin.usd` | Dot-path to the number (`rates.0.value` works too) |
| `TARGET_NAME` | `Bitcoin price (USD)` | Label used in messages |
| `ALERT_MODE` | `change` | `change` · `threshold_above` · `threshold_below` · `report` |
| `THRESHOLD` | — | Required for the threshold modes |

Threshold modes alert **once, on crossing** — not every 30 minutes while the
value sits past the line.

## Portfolio menu bot

```bash
python portfolio_bot.py
```

Edit [projects.json](projects.json) to list your projects (`CHANGE-ME` links
are placeholders). Each entry: `id`, `title`, `description`, optional `image`
(https URL of a screenshot — shown as a photo), `url` (live demo button),
`repo` (source button). The file is validated at startup; bad ids or non-https
links refuse to boot.

This process needs to stay running (Telegram long polling), so run it on your
machine during a demo or on any free worker host. It never conflicts with the
Actions cron — the monitor only *sends* messages, it doesn't poll.

## Tests

```bash
python -m pytest -q
```

Covers: JSON path extraction against a saved sample response, alert/threshold
logic, state read/write round-trip (including a corrupt `state.json`), HTML
escaping, message truncation, and `projects.json` validation.

## Security notes

- Token lives only in env vars / Actions secrets; `.env` is git-ignored. If a
  token ever leaks, revoke it in @BotFather with `/revoke`.
- Network errors are re-raised **sanitized** — `requests` exceptions embed the
  request URL, which contains the token, so they never reach logs verbatim.
- All dynamic text is HTML-escaped before sending; messages are truncated to
  Telegram's limits.
- The menu bot only serves whitelisted content from `projects.json`: callback
  data is validated against known ids, user input is never echoed back, and
  link fields must be `https://`.
- `state.json` is written atomically (temp file + rename) so a killed run
  can't corrupt it — and a corrupt file degrades to "first run", not a crash.

## Honest notes on GitHub Actions cron

Per GitHub's docs (checked 2026-08-27): scheduled runs **can be delayed** under
load, and in public repos schedules are **auto-disabled after 60 days without
repo activity**. Two mitigations built in: `workflow_dispatch` gives a reliable
manual trigger for demos, and the workflow's own `state.json` commits count as
activity. Polling (not webhooks) is the right shape here because the target
API doesn't push events.
