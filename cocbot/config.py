"""Настройки из переменных окружения.

Всё, что зависит от конкретной установки (токены, путь к базе, интервалы),
читается здесь один раз и дальше передаётся явно. Остальной код не знает
про os.environ — так его проще тестировать.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from cocbot.coc.tags import normalize_tag


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
        raise ConfigError(f"{name} должно быть числом, получено: {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    coc_token: str
    coc_base_url: str
    database_path: Path
    poll_interval: int
    log_level: str
    # Необязательная «быстрая настройка» для одного клана: если заданы,
    # группа будет привязана к клану при старте без команды /setclan.
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
        raise ConfigError("Не заданы обязательные переменные: " + ", ".join(missing))

    clan_tag = _get("CLAN_TAG")
    if clan_tag:
        clan_tag = normalize_tag(clan_tag)
        if not clan_tag:
            raise ConfigError("CLAN_TAG выглядит некорректно")

    poll_interval = _get_int("POLL_INTERVAL_SECONDS", 120)
    if poll_interval < 30:
        raise ConfigError("POLL_INTERVAL_SECONDS не может быть меньше 30 секунд")

    return Settings(
        telegram_token=telegram_token,
        coc_token=coc_token,
        coc_base_url=_get("COC_API_BASE_URL", "https://api.clashofclans.com/v1").rstrip("/"),
        database_path=Path(_get("DATABASE_PATH", "data/cocbot.db")),
        poll_interval=poll_interval,
        log_level=_get("LOG_LEVEL", "INFO").upper(),
        bootstrap_chat_id=_get_int("GROUP_CHAT_ID"),
        bootstrap_clan_tag=clan_tag,
        bootstrap_thread_id=_get_int("GROUP_THREAD_ID"),
    )
