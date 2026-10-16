"""Application configuration loaded from the backend environment file."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def parse_cors_origins(value: str | None) -> tuple[str, ...]:
    """Parse and validate a comma-separated HTTP(S) origin allowlist."""
    if value is None:
        return DEFAULT_CORS_ORIGINS

    origins: list[str] = []
    for entry in value.split(","):
        origin = entry.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "CORS_ORIGINS must contain comma-separated HTTP(S) origins without paths or wildcards."
            )
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)


CORS_ORIGINS = parse_cors_origins(os.getenv("CORS_ORIGINS"))

# Recycling Intelligence Agent Configuration
AGENT_ENABLED: bool = os.getenv("AGENT_ENABLED", "").lower() in ("true", "1", "yes")
AGENT_BASE_URL: str = os.getenv("AGENT_BASE_URL", "").rstrip("/")
AGENT_API_KEY: str = os.getenv("AGENT_API_KEY", "").strip()
AGENT_MODEL: str = os.getenv("AGENT_MODEL", "gpt-4o-mini").strip()
AGENT_TIMEOUT_SECONDS: float = float(os.getenv("AGENT_TIMEOUT_SECONDS", "30.0"))
AGENT_MAX_TOOL_ROUNDS: int = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "5"))


def get_agent_config() -> dict[str, Any]:
    """Dynamically reads current agent configuration from environment."""
    enabled_str = os.getenv("AGENT_ENABLED", "true" if AGENT_ENABLED else "false")
    enabled = enabled_str.lower() in ("true", "1", "yes")
    base_url = os.getenv("AGENT_BASE_URL", AGENT_BASE_URL).rstrip("/")
    api_key = os.getenv("AGENT_API_KEY", AGENT_API_KEY).strip()
    model = os.getenv("AGENT_MODEL", AGENT_MODEL).strip() or "gpt-4o-mini"
    timeout_raw = os.getenv("AGENT_TIMEOUT_SECONDS", str(AGENT_TIMEOUT_SECONDS))
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = 30.0
    rounds_raw = os.getenv("AGENT_MAX_TOOL_ROUNDS", str(AGENT_MAX_TOOL_ROUNDS))
    try:
        max_rounds = int(rounds_raw)
    except ValueError:
        max_rounds = 5

    is_configured = bool(enabled and base_url and api_key)
    return {
        "enabled": enabled,
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "timeout_seconds": timeout,
        "max_tool_rounds": max_rounds,
        "is_configured": is_configured,
    }


def is_agent_configured() -> bool:
    """Returns True only when AGENT_ENABLED is True and provider URL + API key are set."""
    return get_agent_config()["is_configured"]
