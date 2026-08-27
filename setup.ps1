# One-command setup: venv + deps + credentials + tests + live smoke test.
# Run from the project folder:  .\setup.ps1
# Optional:                     .\setup.ps1 -Deploy   (also creates the GitHub repo + secrets via gh CLI)
param([switch]$Deploy)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Checking Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "Python not found. Install Python 3.11+ from python.org first." -ForegroundColor Red; exit 1 }
python --version

Step "Creating virtual environment (.venv)"
if (-not (Test-Path ".venv")) { python -m venv .venv }
$pip = ".\.venv\Scripts\pip.exe"
$python = ".\.venv\Scripts\python.exe"

Step "Installing dependencies"
& $pip install --quiet --upgrade pip
& $pip install --quiet -r requirements-dev.txt

Step "Configuring credentials (.env)"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Get a token from @BotFather (/newbot), add the bot to your group as admin."
    $token = Read-Host "Paste TG_TOKEN"
    $chat = Read-Host "Paste TG_CHAT_ID (group ids are usually negative, e.g. -100...)"
    $envText = Get-Content ".env" -Raw
    $envText = $envText -replace "(?m)^TG_TOKEN=.*$", "TG_TOKEN=$token"
    $envText = $envText -replace "(?m)^TG_CHAT_ID=.*$", "TG_CHAT_ID=$chat"
    Set-Content ".env" $envText -Encoding utf8
} else {
    Write-Host ".env already exists - keeping it."
}

Step "Running tests"
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "Tests failed - fix before continuing." -ForegroundColor Red; exit 1 }

Step "Smoke test: sending 'bot is alive' to your Telegram"
& $python monitor.py --test
if ($LASTEXITCODE -ne 0) { Write-Host "Send failed - check TG_TOKEN / TG_CHAT_ID in .env" -ForegroundColor Red; exit 1 }

Step "First real monitor run"
& $python monitor.py
if ($LASTEXITCODE -ne 0) { exit 1 }

if ($Deploy) {
    Step "Deploying to GitHub (public repo + secrets + push)"
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) { Write-Host "gh CLI not found - install from cli.github.com, run 'gh auth login', then re-run with -Deploy." -ForegroundColor Red; exit 1 }
    if (-not (Test-Path ".git")) { git init; git add .; git commit -m "feat: price watch bot + portfolio menu" }
    gh repo create price-watch-bot --public --source . --push
    if ($LASTEXITCODE -ne 0) { Write-Host "Repo create/push failed (maybe it already exists?)" -ForegroundColor Red; exit 1 }
    # Read secrets out of .env and push them to Actions secrets
    foreach ($line in Get-Content ".env") {
        if ($line -match "^(TG_TOKEN|TG_CHAT_ID|TG_ADMIN_CHAT_ID)=(.+)$") {
            gh secret set $Matches[1] --body $Matches[2]
        }
    }
    Write-Host "`nDeployed. Open the repo's Actions tab -> 'monitor' -> 'Run workflow' to demo it." -ForegroundColor Green
}

Write-Host "`nDone. Next steps:" -ForegroundColor Green
Write-Host "  - Portfolio menu bot (interactive):  .\.venv\Scripts\python.exe portfolio_bot.py"
Write-Host "  - Edit projects.json with your real project links/images"
if (-not $Deploy) { Write-Host "  - Deploy to GitHub Actions:          .\setup.ps1 -Deploy" }
