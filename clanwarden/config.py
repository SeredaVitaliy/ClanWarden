"""Settings from environment variables.

Everything installation-specific (tokens, database path, intervals) is read
here once and then passed around explicitly. The rest of the code never
touches os.environ, which keeps it easy to test.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from clanwarden.coc.tags import normalize_tag


class ConfigError(RuntimeError):
    pass


def _get(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _get_int(name: str, default: int | None = None) -> int | None:
    raw = _get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    coc_token: str
    coc_base_url: str
    database_path: Path
    poll_interval: int
    log_level: str
    # Optional single-clan quick setup: if set, the group is connected to the
    # clan on startup without the /setclan command.
    bootstrap_chat_id: int | None
    bootstrap_clan_tag: str | None
    bootstrap_thread_id: int | None


def load_settings(env_file: str | os.PathLike | None = ".env") -> Settings:
    if env_file:
        load_dotenv(env_file)

    telegram_token = _get("TELEGRAM_BOT_TOKEN")
    coc_token = _get("COC_API_TOKEN")
    missing = [
        name
        for name, value in (("TELEGRAM_BOT_TOKEN", telegram_token), ("COC_API_TOKEN", coc_token))
        if not value
    ]
    if missing:
        raise ConfigError("Missing required variables: " + ", ".join(missing))

    clan_tag = _get("CLAN_TAG")
    if clan_tag:
        clan_tag = normalize_tag(clan_tag)
        if not clan_tag:
            raise ConfigError("CLAN_TAG is not a valid tag")

    poll_interval = _get_int("POLL_INTERVAL_SECONDS", 120)
    if poll_interval < 30:
        raise ConfigError("POLL_INTERVAL_SECONDS cannot be less than 30 seconds")

    return Settings(
        telegram_token=telegram_token,
        coc_token=coc_token,
        coc_base_url=_get("COC_API_BASE_URL", "https://api.clashofclans.com/v1").rstrip("/"),
        database_path=Path(_get("DATABASE_PATH", "data/clanwarden.db")),
        poll_interval=poll_interval,
        log_level=_get("LOG_LEVEL", "INFO").upper(),
        bootstrap_chat_id=_get_int("GROUP_CHAT_ID"),
        bootstrap_clan_tag=clan_tag,
        bootstrap_thread_id=_get_int("GROUP_THREAD_ID"),
    )
