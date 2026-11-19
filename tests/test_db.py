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


async def test_war_history_and_stats(db):
    from datetime import timedelta

    from clanwarden.coc.models import War
    from tests.factories import clan, member, war_json

    def finished_war(days_ago, alice_attacks, alice_stars, bob_attacks, result_stars):
        ours = clan(
            "#OURS",
            "Our Clan",
            [member("#P1", "Alice", 1, alice_attacks, alice_stars), member("#P2", "Bob", 2, bob_attacks, 3)],
            stars=result_stars,
        )
        return War.from_api(war_json("warEnded", ours=ours, end_in=-timedelta(days=days_ago)))

    old = finished_war(10, 2, 2, 0, 1)  # 1 star vs 0 for the opponent: a win
    recent = finished_war(1, 2, 3, 1, 6)

    assert await db.record_war(old) is True
    assert await db.record_war(old) is False  # idempotent
    await db.record_war(recent)

    record = await db.war_record("#OURS", limit=10)
    assert (record.wars, record.wins) == (2, 2)

    stats = {s.tag: s for s in await db.clan_player_stats("#OURS", limit=10)}
    alice, bob = stats["#P1"], stats["#P2"]
    assert (alice.wars, alice.attacks_used, alice.stars, alice.triples) == (2, 4, 10, 2)
    assert alice.avg_stars == 2.5
    assert (bob.attacks_used, bob.missed) == (1, 3)

    # Only the last war.
    last = {s.tag: s for s in await db.clan_player_stats("#OURS", limit=1)}
    assert last["#P1"].stars == 6

    history = await db.player_wars("#P1", limit=5)
    assert [h.stars for h in history] == [6, 4]
