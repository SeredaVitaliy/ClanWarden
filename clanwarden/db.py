"""SQLite storage.

SQLite is a deliberate choice: the bot runs as a single container on a small
VPS and writes a few dozen rows per minute. A separate Postgres would only
make installation harder. The schema is versioned with ``PRAGMA user_version``:
each migration is a step that runs exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from clanwarden.coc.models import War

MIGRATIONS: list[str] = [
    # 1: base schema
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

    -- A player tag has exactly one owner, otherwise mentions and reminders
    -- would go to the wrong person. Taking over a tag requires a game token.
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

    -- Journal of delivered notifications. Thanks to it a restart never
    -- re-sends "the war has started".
    CREATE TABLE sent_events (
        target_id  INTEGER NOT NULL,
        war_key    TEXT NOT NULL,
        event      TEXT NOT NULL,
        sent_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (target_id, war_key, event)
    );
    """,
    # 2: interface language for groups and users (NULL = auto / default)
    """
    ALTER TABLE chats ADD COLUMN language TEXT;
    ALTER TABLE users ADD COLUMN language TEXT;
    """,
    # 3: war history for /stats. A war between two tracked clans is stored from
    # each side, hence clan_tag in the keys.
    """
    CREATE TABLE wars (
        war_key              TEXT NOT NULL,
        clan_tag             TEXT NOT NULL,
        opponent_tag         TEXT,
        opponent_name        TEXT,
        is_cwl               INTEGER NOT NULL,
        cwl_season           TEXT,
        team_size            INTEGER NOT NULL,
        stars                INTEGER NOT NULL,
        opponent_stars       INTEGER NOT NULL,
        destruction          REAL NOT NULL,
        opponent_destruction REAL NOT NULL,
        result               TEXT NOT NULL,
        ended_at             TEXT NOT NULL,
        PRIMARY KEY (war_key, clan_tag)
    );
    CREATE INDEX idx_wars_clan ON wars (clan_tag, ended_at);

    CREATE TABLE war_members (
        war_key         TEXT NOT NULL,
        clan_tag        TEXT NOT NULL,
        player_tag      TEXT NOT NULL,
        player_name     TEXT NOT NULL,
        townhall        INTEGER NOT NULL,
        attacks_allowed INTEGER NOT NULL,
        attacks_used    INTEGER NOT NULL,
        stars           INTEGER NOT NULL,
        triples         INTEGER NOT NULL,
        destruction     REAL NOT NULL,
        PRIMARY KEY (war_key, clan_tag, player_tag)
    );
    CREATE INDEX idx_war_members_player ON war_members (player_tag);
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
    language: str | None

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
            language=row["language"],
        )


@dataclass(frozen=True)
class WarRecord:
    wars: int
    wins: int
    losses: int
    ties: int


@dataclass(frozen=True)
class PlayerStats:
    """A player's totals over a set of wars."""

    tag: str
    name: str
    wars: int
    attacks_used: int
    attacks_allowed: int
    stars: int
    triples: int
    destruction: float

    @property
    def missed(self) -> int:
        return self.attacks_allowed - self.attacks_used

    @property
    def avg_stars(self) -> float:
        return self.stars / self.attacks_used if self.attacks_used else 0.0

    @property
    def avg_destruction(self) -> float:
        return self.destruction / self.attacks_used if self.attacks_used else 0.0


@dataclass(frozen=True)
class PlayerWar:
    """One war from a player's history."""

    opponent_name: str
    is_cwl: bool
    ended_at: str
    attacks_used: int
    attacks_allowed: int
    stars: int
    triples: int
    destruction: float


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
            raise RuntimeError("Database.connect() has not been called")
        return self._conn

    async def _migrate(self) -> None:
        async with self.conn.execute("PRAGMA user_version") as cur:
            (version,) = await cur.fetchone()
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            await self.conn.executescript(script)
            await self.conn.execute(f"PRAGMA user_version = {number}")
        await self.conn.commit()

    # --- chats ---

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

    async def _update_chat(self, chat_id: int, column: str, value: object) -> None:
        # `column` only ever comes from the hard-coded callers below, never from user input.
        await self.ensure_chat(chat_id)
        await self.conn.execute(f"UPDATE chats SET {column} = ? WHERE chat_id = ?", (value, chat_id))
        await self.conn.commit()

    async def set_chat_clan(self, chat_id: int, clan_tag: str | None) -> None:
        await self._update_chat(chat_id, "clan_tag", clan_tag)

    async def set_chat_thread(self, chat_id: int, thread_id: int | None) -> None:
        await self._update_chat(chat_id, "thread_id", thread_id)

    async def set_chat_rules(self, chat_id: int, rules: str | None) -> None:
        await self._update_chat(chat_id, "rules", rules)

    async def set_chat_language(self, chat_id: int, language: str | None) -> None:
        await self._update_chat(chat_id, "language", language)

    async def toggle_chat_flag(self, chat_id: int, flag: str) -> None:
        if flag not in CHAT_TOGGLES:
            raise ValueError(f"Unknown setting: {flag}")
        await self.ensure_chat(chat_id)
        await self.conn.execute(f"UPDATE chats SET {flag} = 1 - {flag} WHERE chat_id = ?", (chat_id,))
        await self.conn.commit()

    async def set_chat_number(self, chat_id: int, field: str, value: int) -> None:
        if field not in ("remind_hours", "autodelete_min"):
            raise ValueError(f"Unknown setting: {field}")
        await self._update_chat(chat_id, field, value)

    async def delete_chat(self, chat_id: int) -> None:
        await self.conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        await self.conn.commit()

    async def configured_chats(self) -> list[ChatSettings]:
        async with self.conn.execute("SELECT * FROM chats WHERE clan_tag IS NOT NULL") as cur:
            return [ChatSettings.from_row(r) for r in await cur.fetchall()]

    async def tracked_clans(self) -> list[str]:
        async with self.conn.execute("SELECT DISTINCT clan_tag FROM chats WHERE clan_tag IS NOT NULL") as cur:
            return [r[0] for r in await cur.fetchall()]

    # --- account links ---

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

    # --- users ---

    async def mark_user_started(self, telegram_id: int, language: str | None = None) -> None:
        """The user pressed /start in private chat, so the bot may message them first.

        Their Telegram language is remembered unless they picked one explicitly.
        """
        await self.conn.execute(
            """
            INSERT INTO users (telegram_id, started_bot, language) VALUES (?, 1, ?)
            ON CONFLICT (telegram_id) DO UPDATE SET
                started_bot = 1,
                language = COALESCE(users.language, excluded.language)
            """,
            (telegram_id, language),
        )
        await self.conn.commit()

    async def set_user_language(self, telegram_id: int, language: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO users (telegram_id, language) VALUES (?, ?)
            ON CONFLICT (telegram_id) DO UPDATE SET language = excluded.language
            """,
            (telegram_id, language),
        )
        await self.conn.commit()

    async def user_language(self, telegram_id: int) -> str | None:
        async with self.conn.execute(
            "SELECT language FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def toggle_dm_reminders(self, telegram_id: int) -> bool:
        await self.conn.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (telegram_id,))
        await self.conn.execute(
            "UPDATE users SET dm_reminders = 1 - dm_reminders WHERE telegram_id = ?", (telegram_id,)
        )
        await self.conn.commit()
        return await self.dm_reminders_enabled(telegram_id)

    async def disable_dm_reminders(self, telegram_id: int) -> None:
        await self.conn.execute("UPDATE users SET dm_reminders = 0 WHERE telegram_id = ?", (telegram_id,))
        await self.conn.commit()

    async def dm_reminders_enabled(self, telegram_id: int) -> bool:
        async with self.conn.execute(
            "SELECT dm_reminders FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row[0]) if row else True

    async def dm_recipients(self, telegram_ids: list[int]) -> dict[int, str | None]:
        """Who can be messaged privately (pressed /start, reminders on) → their language."""
        if not telegram_ids:
            return {}
        placeholders = ",".join("?" * len(telegram_ids))
        async with self.conn.execute(
            f"""SELECT telegram_id, language FROM users
                WHERE started_bot = 1 AND dm_reminders = 1 AND telegram_id IN ({placeholders})""",
            telegram_ids,
        ) as cur:
            return {r[0]: r[1] for r in await cur.fetchall()}

    # --- war history ---

    async def record_war(self, war: War) -> bool:
        """Store a finished war and every member's attacks. Idempotent; True if newly stored."""
        moment = war.end or war.start or war.preparation_start
        ended_at = moment.isoformat() if moment else ""
        cur = await self.conn.execute(
            """
            INSERT OR IGNORE INTO wars (
                war_key, clan_tag, opponent_tag, opponent_name, is_cwl, cwl_season, team_size,
                stars, opponent_stars, destruction, opponent_destruction, result, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                war.key, war.clan.tag, war.opponent.tag, war.opponent.name, int(war.is_cwl),
                war.cwl_season, war.team_size, war.clan.stars, war.opponent.stars,
                war.clan.destruction, war.opponent.destruction, war.result.value, ended_at,
            ),
        )  # fmt: skip
        if cur.rowcount == 0:
            await self.conn.commit()
            return False
        await self.conn.executemany(
            """
            INSERT OR IGNORE INTO war_members (
                war_key, clan_tag, player_tag, player_name, townhall,
                attacks_allowed, attacks_used, stars, triples, destruction
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    war.key,
                    war.clan.tag,
                    m.tag,
                    m.name,
                    m.townhall,
                    war.attacks_per_member,
                    len(m.attacks),
                    war.stars_of(m),
                    sum(1 for a in m.attacks if a.stars == 3),
                    sum(a.destruction for a in m.attacks),
                )  # fmt: skip
                for m in war.clan.members
            ],
        )
        await self.conn.commit()
        return True

    @staticmethod
    def _wars_filter(cwl_season: str | None) -> tuple[str, tuple]:
        if cwl_season:
            return "AND is_cwl = 1 AND cwl_season = ?", (cwl_season,)
        return "", ()

    async def war_record(self, clan_tag: str, limit: int, cwl_season: str | None = None) -> WarRecord:
        extra, params = self._wars_filter(cwl_season)
        async with self.conn.execute(
            f"""
            SELECT result, COUNT(*) FROM (
                SELECT result FROM wars WHERE clan_tag = ? {extra} ORDER BY ended_at DESC LIMIT ?
            ) GROUP BY result
            """,
            (clan_tag, *params, limit),
        ) as cur:
            counts = {row[0]: row[1] for row in await cur.fetchall()}
        wins, losses, ties = counts.get("win", 0), counts.get("lose", 0), counts.get("tie", 0)
        return WarRecord(wars=wins + losses + ties, wins=wins, losses=losses, ties=ties)

    async def clan_player_stats(
        self, clan_tag: str, limit: int, cwl_season: str | None = None
    ) -> list[PlayerStats]:
        """Per-player totals over the clan's last `limit` recorded wars (or one CWL season)."""
        extra, params = self._wars_filter(cwl_season)
        async with self.conn.execute(
            f"""
            WITH recent AS (
                SELECT war_key FROM wars WHERE clan_tag = ? {extra} ORDER BY ended_at DESC LIMIT ?
            )
            SELECT player_tag,
                   (SELECT player_name FROM war_members m2 JOIN wars w2 USING (war_key, clan_tag)
                    WHERE m2.player_tag = m.player_tag ORDER BY w2.ended_at DESC LIMIT 1),
                   COUNT(*), SUM(attacks_used), SUM(attacks_allowed), SUM(stars), SUM(triples),
                   SUM(destruction)
            FROM war_members m
            WHERE clan_tag = ? AND war_key IN (SELECT war_key FROM recent)
            GROUP BY player_tag
            """,
            (clan_tag, *params, limit, clan_tag),
        ) as cur:
            return [PlayerStats(*row) for row in await cur.fetchall()]

    async def player_wars(self, player_tag: str, limit: int) -> list[PlayerWar]:
        async with self.conn.execute(
            """
            SELECT w.opponent_name, w.is_cwl, w.ended_at, m.attacks_used, m.attacks_allowed,
                   m.stars, m.triples, m.destruction
            FROM war_members m JOIN wars w USING (war_key, clan_tag)
            WHERE m.player_tag = ?
            ORDER BY w.ended_at DESC LIMIT ?
            """,
            (player_tag, limit),
        ) as cur:
            return [PlayerWar(r[0], bool(r[1]), *r[2:]) for r in await cur.fetchall()]

    async def player_name(self, player_tag: str) -> str | None:
        async with self.conn.execute(
            """
            SELECT m.player_name FROM war_members m JOIN wars w USING (war_key, clan_tag)
            WHERE m.player_tag = ? ORDER BY w.ended_at DESC LIMIT 1
            """,
            (player_tag,),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def latest_cwl_season(self, clan_tag: str) -> str | None:
        async with self.conn.execute(
            "SELECT MAX(cwl_season) FROM wars WHERE clan_tag = ? AND is_cwl = 1", (clan_tag,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    # --- notification journal ---

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
