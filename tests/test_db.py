import pytest

from clanwarden.db import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def test_migrations_are_idempotent(tmp_path):
    path = tmp_path / "again.db"
    for _ in range(2):
        database = Database(path)
        await database.connect()
        await database.close()


async def test_chat_settings_and_toggles(db):
    chat = await db.ensure_chat(-100)
    assert chat.clan_tag is None and chat.notify_remind is True

    await db.set_chat_clan(-100, "#2PP")
    await db.toggle_chat_flag(-100, "notify_remind")
    await db.set_chat_number(-100, "remind_hours", 6)
    chat = await db.get_chat(-100)
    assert (chat.clan_tag, chat.notify_remind, chat.remind_hours) == ("#2PP", False, 6)
    assert await db.tracked_clans() == ["#2PP"]

    with pytest.raises(ValueError):
        await db.toggle_chat_flag(-100, "clan_tag; DROP TABLE chats")


async def test_links_are_unique_per_tag(db):
    await db.save_link("#P1", 1, "Alice", verified=False)
    await db.save_link("#P1", 2, "Alice", verified=True)  # re-link with verification

    link = await db.get_link("#P1")
    assert (link.telegram_id, link.verified) == (2, True)
    assert await db.user_links(1) == []
    assert not await db.delete_link("#P1", 1)  # can't delete someone else's link
    assert await db.delete_link("#P1", 2)


async def test_dm_recipients_require_start(db):
    await db.toggle_dm_reminders(1)  # turned off
    await db.mark_user_started(2)
    await db.mark_user_started(3)
    await db.toggle_dm_reminders(3)  # turned off
    assert await db.dm_recipients([1, 2, 3, 4]) == {2: None}


async def test_sent_events_journal(db):
    await db.mark_sent(-100, "war:1", "start")
    await db.mark_sent(-100, "war:1", "start")  # a duplicate is fine
    assert await db.sent_events(-100, "war:1") == {"start"}
    assert await db.sent_events(-100, "war:2") == set()
