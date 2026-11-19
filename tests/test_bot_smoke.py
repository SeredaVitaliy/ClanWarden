"""End-to-end run of the aiogram dispatcher on fake updates.

Telegram is replaced by a session that records method calls and returns
plausible responses; the CoC API by a stub. This checks the whole chain:
middleware → filters → handler → database → reply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageText,
    GetChatMember,
    SendChatAction,
    SendMessage,
)
from aiogram.types import ChatMemberAdministrator, ChatMemberMember, Message, Update, User

from clanwarden.app import build_dispatcher
from clanwarden.coc.models import Clan, ClanMember, Player, PlayerClan, War
from clanwarden.db import Database
from clanwarden.services.wars import WarService
from tests.factories import war_json

BOT_USER = User(id=999, is_bot=True, first_name="Bot", username="cocwarbot")
ADMIN_ID, PLAYER_ID, GROUP_ID = 1, 2, -1001


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109 — aiogram signature
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message.model_validate(
                {
                    "message_id": len(self.calls),
                    "date": 0,
                    "chat": {"id": method.chat_id, "type": "supergroup" if method.chat_id < 0 else "private"},
                    "from": BOT_USER.model_dump(),
                    "text": method.text,
                }
            )
        if isinstance(method, GetChatMember):
            if method.user_id == ADMIN_ID:
                # model_construct: the set of required fields changes between Bot API versions.
                return ChatMemberAdministrator.model_construct(
                    status="administrator", user=User(id=ADMIN_ID, is_bot=False, first_name="Admin")
                )
            return ChatMemberMember(user=User(id=method.user_id, is_bot=False, first_name="U"))
        if isinstance(method, (EditMessageText, AnswerCallbackQuery, SendChatAction, DeleteMessage)):
            return True
        raise AssertionError(f"Unexpected method {type(method).__name__}")

    def texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, (SendMessage, EditMessageText))]


class FakeCoc:
    async def get_clan(self, tag):
        members = (ClanMember("#P1", "Alice", "leader"), ClanMember("#P2", "Bob", "member"))
        return Clan(tag=tag, name="Our Clan", level=10, war_log_public=True, members=members)

    async def get_player(self, tag):
        return Player(tag=tag, name="Bob", townhall=15, clan=PlayerClan("#OURS", "Our Clan"))

    async def get_current_war(self, tag):
        return War.from_api(war_json(end_in=timedelta(hours=5)))

    async def get_league_group(self, tag):
        return None

    async def verify_player_token(self, tag, token):
        return token == "good"


_update_id = 0


def msg_update(
    text: str, *, chat_id: int, user_id: int, thread_id: int | None = None, lang: str | None = None
) -> Update:
    global _update_id
    _update_id += 1
    chat_type = "supergroup" if chat_id < 0 else "private"
    data = {
        "message_id": _update_id,
        "date": int(datetime.now(UTC).timestamp()),
        "chat": {"id": chat_id, "type": chat_type, "is_forum": thread_id is not None},
        "from": {"id": user_id, "is_bot": False, "first_name": "User", "language_code": lang},
        "text": text,
    }
    if text.startswith("/"):
        data["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    if thread_id:
        data["message_thread_id"] = thread_id
        data["is_topic_message"] = True
    return Update(update_id=_update_id, message=data)


def callback_update(data: str, *, chat_id: int, user_id: int) -> Update:
    global _update_id
    _update_id += 1
    return Update.model_validate(
        {
            "update_id": _update_id,
            "callback_query": {
                "id": str(_update_id),
                "chat_instance": "x",
                "from": {"id": user_id, "is_bot": False, "first_name": "User"},
                "data": data,
                "message": {
                    "message_id": 500,
                    "date": 0,
                    "chat": {"id": chat_id, "type": "supergroup" if chat_id < 0 else "private"},
                    "from": BOT_USER.model_dump(),
                    "text": "menu",
                },
            },
        }
    )


_DP = None


def _dispatcher():
    global _DP
    if _DP is None:
        _DP = build_dispatcher(None, None, None)
    return _DP


@pytest.fixture
async def env(tmp_path):
    db = Database(tmp_path / "bot.db")
    await db.connect()
    session = FakeSession()
    bot = Bot("123:ABC", session=session)
    bot._me = BOT_USER
    coc = FakeCoc()
    dp = _dispatcher()
    # aiogram routers can be attached to a dispatcher only once per process,
    # so the dispatcher is shared and dependencies are swapped per test.
    dp["db"], dp["coc"], dp["wars"] = db, coc, WarService(coc)

    async def feed(update: Update) -> list[str]:
        before = len(session.texts())
        await dp.feed_update(bot, update)
        return session.texts()[before:]

    yield feed, db, session
    await db.close()


async def test_group_setup_and_war_flow(env):
    feed, db, _ = env

    # A regular member can't connect a clan.
    out = await feed(msg_update("/setclan #2PP", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "Only group admins" in out[0]
    assert (await db.get_chat(GROUP_ID)).clan_tag is None

    out = await feed(msg_update("/setclan #2PP", chat_id=GROUP_ID, user_id=ADMIN_ID))
    assert "now connected to" in out[0]
    assert (await db.get_chat(GROUP_ID)).clan_tag == "#2PP"

    out = await feed(msg_update("/war", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "Battle day" in out[0] and "Our Clan" in out[0]

    out = await feed(msg_update("/missed@cocwarbot", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "Bob" in out[0] and "Alice" not in out[0]


async def test_setclan_adopts_admin_language(env):
    feed, db, _ = env
    out = await feed(msg_update("/setclan #2PP", chat_id=GROUP_ID, user_id=ADMIN_ID, lang="ru"))
    assert "Группа привязана" in out[0]
    assert (await db.get_chat(GROUP_ID)).language == "ru"

    # From now on the group gets Russian regardless of who writes.
    out = await feed(msg_update("/war", chat_id=GROUP_ID, user_id=PLAYER_ID, lang="en"))
    assert "День атак" in out[0]


async def test_language_switch(env):
    feed, db, _ = env
    # Private chat: Telegram language is used until the user picks one.
    out = await feed(msg_update("/help", chat_id=PLAYER_ID, user_id=PLAYER_ID, lang="ru-RU"))
    assert "Привет" in out[0]

    await feed(msg_update("/language", chat_id=PLAYER_ID, user_id=PLAYER_ID, lang="ru"))
    out = await feed(callback_update("l:en", chat_id=PLAYER_ID, user_id=PLAYER_ID))
    assert "English" in out[0]
    out = await feed(msg_update("/help", chat_id=PLAYER_ID, user_id=PLAYER_ID, lang="ru"))
    assert "Hi! I'm Clan Warden" in out[0]

    # Group: only admins can switch.
    await feed(callback_update("l:ru", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert (await db.get_chat(GROUP_ID)).language is None
    await feed(callback_update("l:ru", chat_id=GROUP_ID, user_id=ADMIN_ID))
    assert (await db.get_chat(GROUP_ID)).language == "ru"


async def test_link_flow_and_ownership(env):
    feed, db, _ = env
    out = await feed(msg_update("/link #2PP", chat_id=PLAYER_ID, user_id=PLAYER_ID))
    assert "linked" in out[0]

    # Someone else can't take the tag without a token...
    out = await feed(msg_update("/link #2PP", chat_id=3, user_id=3))
    assert "already linked by someone else" in out[0]
    # ...but can with a valid one.
    out = await feed(msg_update("/link #2PP good", chat_id=3, user_id=3))
    assert "verified" in out[0]
    assert (await db.get_link("#2PP")).telegram_id == 3

    out = await feed(msg_update("/me", chat_id=3, user_id=3))
    assert "Bob" in out[0]


async def test_topic_filter(env):
    feed, db, _ = env
    await db.set_chat_clan(GROUP_ID, "#2PP")
    await db.set_chat_thread(GROUP_ID, 77)

    assert await feed(msg_update("/war", chat_id=GROUP_ID, user_id=PLAYER_ID, thread_id=5)) == []
    assert await feed(msg_update("/war", chat_id=GROUP_ID, user_id=PLAYER_ID, thread_id=77))
    assert await feed(msg_update("@cocwarbot hi", chat_id=GROUP_ID, user_id=PLAYER_ID, thread_id=5)) == []
    # The topic can be changed from any topic.
    out = await feed(msg_update("/settopic", chat_id=GROUP_ID, user_id=ADMIN_ID, thread_id=5))
    assert "only in this topic" in out[0]
    assert (await db.get_chat(GROUP_ID)).thread_id == 5


async def test_menu_and_settings_callbacks(env):
    feed, db, _ = env
    await db.set_chat_clan(GROUP_ID, "#2PP")

    out = await feed(callback_update("m:war", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "Battle day" in out[0]

    # A non-admin can't change settings.
    await feed(callback_update("s:notify_end", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert (await db.get_chat(GROUP_ID)).notify_end is True

    out = await feed(callback_update("s:notify_end", chat_id=GROUP_ID, user_id=ADMIN_ID))
    assert (await db.get_chat(GROUP_ID)).notify_end is False
    assert "Group settings" in out[0]

    await feed(callback_update("s:remind_hours", chat_id=GROUP_ID, user_id=ADMIN_ID))
    assert (await db.get_chat(GROUP_ID)).remind_hours == 4


async def test_private_start_marks_user(env):
    feed, db, _ = env
    out = await feed(msg_update("/start", chat_id=PLAYER_ID, user_id=PLAYER_ID, lang="ru"))
    assert "Clan Warden" in out[0]
    assert await db.dm_recipients([PLAYER_ID]) == {PLAYER_ID: "ru"}

    out = await feed(msg_update("hello", chat_id=PLAYER_ID, user_id=PLAYER_ID))
    assert "/menu" in out[0]


async def test_stats_command(env):
    from tests.factories import clan, member

    feed, db, _ = env
    await db.set_chat_clan(GROUP_ID, "#OURS")

    out = await feed(msg_update("/stats", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "No finished wars recorded yet" in out[0]

    ours = clan("#OURS", "Our Clan", [member("#2PP", "Alice", 1, 2, 3), member("#2PQ", "Bob", 2, 0)], stars=6)
    await db.record_war(War.from_api(war_json("warEnded", ours=ours, end_in=-timedelta(hours=1))))

    out = await feed(msg_update("/stats", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "1. Alice — ⭐6" in out[0]
    assert "Bob — 2/2" in out[0]  # missed both attacks

    # "200" is a valid tag syntactically, but a bare number means "how many wars".
    out = await feed(msg_update("/stats 200", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "wars counted: 1" in out[0]

    out = await feed(msg_update("/stats #2PP", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "Alice" in out[0] and "attacks 2/2" in out[0]

    out = await feed(msg_update("/stats cwl", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "No CWL wars recorded yet" in out[0]
