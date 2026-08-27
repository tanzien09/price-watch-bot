"""Environment/config loading. Stdlib only — no python-dotenv dependency needed."""

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ.

    Real environment variables win over the file (setdefault), so GitHub
    Actions secrets are never overridden by a stray committed file.
    """
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require(name: str) -> str:
    value = get(name)
    if not value:
        raise SystemExit(
            f"Missing required environment variable {name!r}. "
            "Copy .env.example to .env and fill it in, or set it in the environment "
            "(GitHub: repo Settings -> Secrets and variables -> Actions)."
        )
    return value


def require_float(name: str) -> float:
    raw = require(name)
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a number, got {raw!r}") from None
