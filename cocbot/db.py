"""Хранилище на SQLite.

SQLite выбран осознанно: бот ставится одним контейнером на маленький VPS,
нагрузка — десятки записей в минуту. Отдельный Postgres тут только усложнил
бы установку. Схема версионируется через PRAGMA user_version: каждая
миграция — это шаг, который выполняется один раз.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite

MIGRATIONS: list[str] = [
    # 1: базовая схема
    """
    CREATE TABLE chats (
        chat_id         INTEGER PRIMARY KEY,
        clan_tag        TEXT,
        thread_id       INTEGER,
        remind_hours    INTEGER NOT NULL DEFAULT 3,
        notify_prep     INTEGER NOT NULL DEFAULT 1,
        notify_start    INTEGER NOT NULL DEFAULT 1,
        notify_remind   INTEGER NOT NULL DEFAULT 1,
        notify_end      INTEGER NOT NULL DEFAULT 1,
        mention_players INTEGER NOT NULL DEFAULT 1,
        autodelete_min  INTEGER NOT NULL DEFAULT 0,
        rules           TEXT,
        created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_chats_clan ON chats (clan_tag);

    -- Тег принадлежит одному человеку: иначе напоминания и упоминания
    -- уходили бы не тому. Передать тег другому можно только через проверку токеном.
    CREATE TABLE links (
        player_tag   TEXT PRIMARY KEY,
        telegram_id  INTEGER NOT NULL,
        player_name  TEXT,
        verified     INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_links_user ON links (telegram_id);

    CREATE TABLE users (
        telegram_id  INTEGER PRIMARY KEY,
        dm_reminders INTEGER NOT NULL DEFAULT 1,
        started_bot  INTEGER NOT NULL DEFAULT 0
    );

    -- Журнал отправленных уведомлений. Благодаря нему перезапуск бота
    -- не приводит к повторной рассылке «война началась».
    CREATE TABLE sent_events (
        target_id  INTEGER NOT NULL,
        war_key    TEXT NOT NULL,
        event      TEXT NOT NULL,
        sent_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (target_id, war_key, event)
    );
    """,
]

CHAT_TOGGLES = ("notify_prep", "notify_start", "notify_remind", "notify_end", "mention_players")


@dataclass(frozen=True)
class ChatSettings:
    chat_id: int
    clan_tag: str | None
    thread_id: int | None
    remind_hours: int
    notify_prep: bool
    notify_start: bool
    notify_remind: bool
    notify_end: bool
    mention_players: bool
    autodelete_min: int
    rules: str | None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> ChatSettings:
        return cls(
            chat_id=row["chat_id"],
            clan_tag=row["clan_tag"],
            thread_id=row["thread_id"],
            remind_hours=row["remind_hours"],
            notify_prep=bool(row["notify_prep"]),
            notify_start=bool(row["notify_start"]),
            notify_remind=bool(row["notify_remind"]),
            notify_end=bool(row["notify_end"]),
            mention_players=bool(row["mention_players"]),
            autodelete_min=row["autodelete_min"],
            rules=row["rules"],
        )


@dataclass(frozen=True)
class Link:
    player_tag: str
    telegram_id: int
    player_name: str | None
    verified: bool


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._migrate()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database.connect() не был вызван")
        return self._conn

    async def _migrate(self) -> None:
        async with self.conn.execute("PRAGMA user_version") as cur:
            (version,) = await cur.fetchone()
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            await self.conn.executescript(script)
            await self.conn.execute(f"PRAGMA user_version = {number}")
        await self.conn.commit()

    # --- чаты ---

    async def get_chat(self, chat_id: int) -> ChatSettings | None:
        async with self.conn.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,)) as cur:
            row = await cur.fetchone()
        return ChatSettings.from_row(row) if row else None

    async def ensure_chat(self, chat_id: int) -> ChatSettings:
        await self.conn.execute("INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (chat_id,))
        await self.conn.commit()
        chat = await self.get_chat(chat_id)
        assert chat is not None
        return chat

    async def set_chat_clan(self, chat_id: int, clan_tag: str | None) -> None:
        await self.ensure_chat(chat_id)
        await self.conn.execute("UPDATE chats SET clan_tag = ? WHERE chat_id = ?", (clan_tag, chat_id))
        await self.conn.commit()

    async def set_chat_thread(self, chat_id: int, thread_id: int | None) -> None:
        await self.ensure_chat(chat_id)
        await self.conn.execute("UPDATE chats SET thread_id = ? WHERE chat_id = ?", (thread_id, chat_id))
        await self.conn.commit()

    async def set_chat_rules(self, chat_id: int, rules: str | None) -> None:
        await self.ensure_chat(chat_id)
        await self.conn.execute("UPDATE chats SET rules = ? WHERE chat_id = ?", (rules, chat_id))
        await self.conn.commit()

    async def toggle_chat_flag(self, chat_id: int, flag: str) -> None:
        if flag not in CHAT_TOGGLES:
            raise ValueError(f"Неизвестная настройка: {flag}")
        await self.ensure_chat(chat_id)
        # Имя колонки берётся только из белого списка выше — подстановка безопасна.
        await self.conn.execute(f"UPDATE chats SET {flag} = 1 - {flag} WHERE chat_id = ?", (chat_id,))
        await self.conn.commit()

    async def set_chat_number(self, chat_id: int, field: str, value: int) -> None:
        if field not in ("remind_hours", "autodelete_min"):
            raise ValueError(f"Неизвестная настройка: {field}")
        await self.ensure_chat(chat_id)
        await self.conn.execute(f"UPDATE chats SET {field} = ? WHERE chat_id = ?", (value, chat_id))
        await self.conn.commit()

    async def delete_chat(self, chat_id: int) -> None:
        await self.conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        await self.conn.commit()

    async def configured_chats(self) -> list[ChatSettings]:
        async with self.conn.execute("SELECT * FROM chats WHERE clan_tag IS NOT NULL") as cur:
            return [ChatSettings.from_row(r) for r in await cur.fetchall()]

    async def tracked_clans(self) -> list[str]:
        async with self.conn.execute("SELECT DISTINCT clan_tag FROM chats WHERE clan_tag IS NOT NULL") as cur:
            return [r[0] for r in await cur.fetchall()]

    # --- привязки аккаунтов ---

    async def get_link(self, player_tag: str) -> Link | None:
        async with self.conn.execute("SELECT * FROM links WHERE player_tag = ?", (player_tag,)) as cur:
            row = await cur.fetchone()
        return _link(row) if row else None

    async def save_link(self, player_tag: str, telegram_id: int, name: str | None, verified: bool) -> None:
        await self.conn.execute(
            """
            INSERT INTO links (player_tag, telegram_id, player_name, verified)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (player_tag) DO UPDATE SET
                telegram_id = excluded.telegram_id,
                player_name = excluded.player_name,
                verified    = excluded.verified
            """,
            (player_tag, telegram_id, name, int(verified)),
        )
        await self.conn.commit()

    async def delete_link(self, player_tag: str, telegram_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM links WHERE player_tag = ? AND telegram_id = ?", (player_tag, telegram_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def user_links(self, telegram_id: int) -> list[Link]:
        async with self.conn.execute(
            "SELECT * FROM links WHERE telegram_id = ? ORDER BY created_at", (telegram_id,)
        ) as cur:
            return [_link(r) for r in await cur.fetchall()]

    async def links_for_tags(self, tags: list[str]) -> dict[str, Link]:
        if not tags:
            return {}
        placeholders = ",".join("?" * len(tags))
        async with self.conn.execute(
            f"SELECT * FROM links WHERE player_tag IN ({placeholders})", tags
        ) as cur:
            return {r["player_tag"]: _link(r) for r in await cur.fetchall()}

    # --- пользователи ---

    async def mark_user_started(self, telegram_id: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO users (telegram_id, started_bot) VALUES (?, 1)
            ON CONFLICT (telegram_id) DO UPDATE SET started_bot = 1
            """,
            (telegram_id,),
        )
        await self.conn.commit()

    async def toggle_dm_reminders(self, telegram_id: int) -> bool:
        await self.conn.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (telegram_id,))
        await self.conn.execute(
            "UPDATE users SET dm_reminders = 1 - dm_reminders WHERE telegram_id = ?", (telegram_id,)
        )
        await self.conn.commit()
        return await self.dm_reminders_enabled(telegram_id)

    async def dm_reminders_enabled(self, telegram_id: int) -> bool:
        async with self.conn.execute(
            "SELECT dm_reminders FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row[0]) if row else True

    async def dm_recipients(self, telegram_ids: list[int]) -> set[int]:
        """Кому можно писать в личку: человек нажал /start и не выключил напоминания."""
        if not telegram_ids:
            return set()
        placeholders = ",".join("?" * len(telegram_ids))
        async with self.conn.execute(
            f"""SELECT telegram_id FROM users
                WHERE started_bot = 1 AND dm_reminders = 1 AND telegram_id IN ({placeholders})""",
            telegram_ids,
        ) as cur:
            return {r[0] for r in await cur.fetchall()}

    # --- журнал уведомлений ---

    async def sent_events(self, target_id: int, war_key: str) -> set[str]:
        async with self.conn.execute(
            "SELECT event FROM sent_events WHERE target_id = ? AND war_key = ?", (target_id, war_key)
        ) as cur:
            return {r[0] for r in await cur.fetchall()}

    async def mark_sent(self, target_id: int, war_key: str, event: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO sent_events (target_id, war_key, event) VALUES (?, ?, ?)",
            (target_id, war_key, event),
        )
        await self.conn.commit()

    async def prune_sent_events(self, days: int = 30) -> None:
        await self.conn.execute(
            "DELETE FROM sent_events WHERE sent_at < datetime('now', ?)", (f"-{days} days",)
        )
        await self.conn.commit()


def _link(row: aiosqlite.Row) -> Link:
    return Link(
        player_tag=row["player_tag"],
        telegram_id=row["telegram_id"],
        player_name=row["player_name"],
        verified=bool(row["verified"]),
    )
