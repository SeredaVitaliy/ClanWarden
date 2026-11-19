"""End-to-end test of the notification loop: real database, stubbed Telegram and API."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from clanwarden.coc.models import War
from clanwarden.db import Database
from clanwarden.services.notifier import Notifier
from tests.factories import NOW, war_json


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, int | None]] = []

    async def send_message(self, chat_id, text, message_thread_id=None, **kwargs):
        self.sent.append((chat_id, text, message_thread_id))
        return SimpleNamespace(message_id=len(self.sent))


class FakeWars:
    def __init__(self, wars):
        self.wars = wars
        self.calls = 0

    async def active_wars(self, clan_tag):
        self.calls += 1
        return self.wars


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def test_reminder_is_sent_once_with_mentions_and_dm(db):
    war = War.from_api(war_json(end_in=timedelta(hours=2)))
    await db.set_chat_clan(-100, "#OURS")
    await db.set_chat_thread(-100, 7)
    await db.save_link("#P2", 42, "Bob", verified=True)
    await db.mark_user_started(42)

    bot, wars = FakeBot(), FakeWars([war])
    notifier = Notifier(bot, db, wars, interval=60)

    await notifier.tick(now=NOW)
    group_msgs = [m for m in bot.sent if m[0] == -100]
    dm_msgs = [m for m in bot.sent if m[0] == 42]
    assert len(group_msgs) == 1 and group_msgs[0][2] == 7  # into the right topic
    assert "tg://user?id=42" in group_msgs[0][1]
    assert len(dm_msgs) == 1 and "Bob" in dm_msgs[0][1]

    # Another poll (or a bot restart) duplicates nothing.
    await notifier.tick(now=NOW + timedelta(minutes=2))
    assert len(bot.sent) == 2


async def test_one_api_call_per_clan_for_many_chats(db):
    war = War.from_api(war_json("warEnded", end_in=-timedelta(minutes=10)))
    await db.set_chat_clan(-100, "#OURS")
    await db.set_chat_clan(-200, "#OURS")

    bot, wars = FakeBot(), FakeWars([war])
    await Notifier(bot, db, wars, interval=60).tick(now=NOW)

    assert wars.calls == 1
    assert sorted(m[0] for m in bot.sent) == [-200, -100]
    # The finished war is saved to history once, not once per chat.
    assert (await db.war_record("#OURS", limit=10)).wars == 1
