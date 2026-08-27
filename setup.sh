#!/usr/bin/env bash
# One-command setup for Linux/macOS:  ./setup.sh   (add --deploy to also push to GitHub)
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }

step "Checking Python"
command -v python3 >/dev/null || { echo "Python 3 not found"; exit 1; }
python3 --version

step "Creating virtual environment (.venv)"
[ -d .venv ] || python3 -m venv .venv
PY=".venv/bin/python"

step "Installing dependencies"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements-dev.txt

step "Configuring credentials (.env)"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Get a token from @BotFather (/newbot), add the bot to your group as admin."
    read -rp "Paste TG_TOKEN: " token
    read -rp "Paste TG_CHAT_ID: " chat
    sed -i.bak -e "s|^TG_TOKEN=.*|TG_TOKEN=$token|" -e "s|^TG_CHAT_ID=.*|TG_CHAT_ID=$chat|" .env
    rm -f .env.bak
else
    echo ".env already exists - keeping it."
fi

step "Running tests"
"$PY" -m pytest -q

step "Smoke test: sending 'bot is alive' to your Telegram"
"$PY" monitor.py --test

step "First real monitor run"
"$PY" monitor.py

if [ "${1:-}" = "--deploy" ]; then
    step "Deploying to GitHub (public repo + secrets + push)"
    command -v gh >/dev/null || { echo "gh CLI not found - install from cli.github.com and 'gh auth login' first"; exit 1; }
    [ -d .git ] || { git init; git add .; git commit -m "feat: price watch bot"; }
    gh repo create price-watch-bot --public --source . --push
    grep -E '^(TG_TOKEN|TG_CHAT_ID|TG_ADMIN_CHAT_ID)=.+' .env | while IFS='=' read -r k v; do
        gh secret set "$k" --body "$v"
    done
    echo "Deployed. Open the repo's Actions tab -> monitor -> Run workflow to demo it."
fi

printf '\n\033[32mDone.\033[0m\n'
