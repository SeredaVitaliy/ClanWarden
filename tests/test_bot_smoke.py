"""Сквозной прогон диспетчера aiogram на фейковых апдейтах.

Telegram подменён сессией, которая записывает вызовы методов и отдаёт
правдоподобные ответы; CoC API — заглушкой. Проверяем связку целиком:
middleware → фильтры → хендлер → база → ответ.
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

from cocbot.app import build_dispatcher
from cocbot.coc.models import Clan, ClanMember, Player, PlayerClan, War
from cocbot.db import Database
from cocbot.services.wars import WarService
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

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109 — сигнатура aiogram
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
                # model_construct: набор обязательных полей меняется от версии к версии API.
                return ChatMemberAdministrator.model_construct(
                    status="administrator", user=User(id=ADMIN_ID, is_bot=False, first_name="Admin")
                )
            return ChatMemberMember(user=User(id=method.user_id, is_bot=False, first_name="U"))
        if isinstance(method, (EditMessageText, AnswerCallbackQuery, SendChatAction, DeleteMessage)):
            return True
        raise AssertionError(f"Неожиданный метод {type(method).__name__}")

    def texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, (SendMessage, EditMessageText))]


class FakeCoc:
    async def get_clan(self, tag):
        members = (ClanMember("#P1", "Alice", "leader"), ClanMember("#P2", "Bob", "member"))
        return Clan(tag=tag, name="Наши", level=10, war_log_public=True, members=members)

    async def get_player(self, tag):
        return Player(tag=tag, name="Bob", townhall=15, clan=PlayerClan("#OURS", "Наши"))

    async def get_current_war(self, tag):
        return War.from_api(war_json(end_in=timedelta(hours=5)))

    async def get_league_group(self, tag):
        return None

    async def verify_player_token(self, tag, token):
        return token == "good"


_update_id = 0


def msg_update(text: str, *, chat_id: int, user_id: int, thread_id: int | None = None) -> Update:
    global _update_id
    _update_id += 1
    chat_type = "supergroup" if chat_id < 0 else "private"
    data = {
        "message_id": _update_id,
        "date": int(datetime.now(UTC).timestamp()),
        "chat": {"id": chat_id, "type": chat_type, "is_forum": thread_id is not None},
        "from": {"id": user_id, "is_bot": False, "first_name": "User"},
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
                    "chat": {"id": chat_id, "type": "supergroup"},
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
    # Роутеры aiogram подключаются к диспетчеру один раз на процесс,
    # поэтому диспетчер общий, а зависимости подменяем на каждый тест.
    dp["db"], dp["coc"], dp["wars"] = db, coc, WarService(coc)

    async def feed(update: Update) -> list[str]:
        before = len(session.texts())
        await dp.feed_update(bot, update)
        return session.texts()[before:]

    yield feed, db, session
    await db.close()


async def test_group_setup_and_war_flow(env):
    feed, db, _ = env

    # Обычный участник не может привязать клан.
    out = await feed(msg_update("/setclan #2PP", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "только админам" in out[0]
    assert (await db.get_chat(GROUP_ID)).clan_tag is None

    out = await feed(msg_update("/setclan #2PP", chat_id=GROUP_ID, user_id=ADMIN_ID))
    assert "привязана к клану" in out[0]
    assert (await db.get_chat(GROUP_ID)).clan_tag == "#2PP"

    out = await feed(msg_update("/war", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "День атак" in out[0] and "Наши" in out[0]

    out = await feed(msg_update("/missed@cocwarbot", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "Bob" in out[0] and "Alice" not in out[0]


async def test_link_flow_and_ownership(env):
    feed, db, _ = env
    out = await feed(msg_update("/link #2PP", chat_id=PLAYER_ID, user_id=PLAYER_ID))
    assert "привязан" in out[0]

    # Другой человек не может занять тег без токена…
    out = await feed(msg_update("/link #2PP", chat_id=3, user_id=3))
    assert "уже привязан другим" in out[0]
    # …а с правильным токеном — может.
    out = await feed(msg_update("/link #2PP good", chat_id=3, user_id=3))
    assert "подтверждён" in out[0]
    assert (await db.get_link("#2PP")).telegram_id == 3

    out = await feed(msg_update("/me", chat_id=3, user_id=3))
    assert "Bob" in out[0]


async def test_topic_filter(env):
    feed, db, _ = env
    await db.set_chat_clan(GROUP_ID, "#2PP")
    await db.set_chat_thread(GROUP_ID, 77)

    assert await feed(msg_update("/war", chat_id=GROUP_ID, user_id=PLAYER_ID, thread_id=5)) == []
    assert await feed(msg_update("/war", chat_id=GROUP_ID, user_id=PLAYER_ID, thread_id=77))
    assert await feed(msg_update("@cocwarbot привет", chat_id=GROUP_ID, user_id=PLAYER_ID, thread_id=5)) == []
    # Настройку темы можно поменять из любой темы.
    out = await feed(msg_update("/settopic", chat_id=GROUP_ID, user_id=ADMIN_ID, thread_id=5))
    assert "только в этой теме" in out[0]
    assert (await db.get_chat(GROUP_ID)).thread_id == 5


async def test_menu_and_settings_callbacks(env):
    feed, db, session = env
    await db.set_chat_clan(GROUP_ID, "#2PP")

    out = await feed(callback_update("m:war", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert "День атак" in out[0]

    # Не-админ не может менять настройки.
    await feed(callback_update("s:notify_end", chat_id=GROUP_ID, user_id=PLAYER_ID))
    assert (await db.get_chat(GROUP_ID)).notify_end is True

    out = await feed(callback_update("s:notify_end", chat_id=GROUP_ID, user_id=ADMIN_ID))
    assert (await db.get_chat(GROUP_ID)).notify_end is False
    assert "Настройки группы" in out[0]

    await feed(callback_update("s:remind_hours", chat_id=GROUP_ID, user_id=ADMIN_ID))
    assert (await db.get_chat(GROUP_ID)).remind_hours == 4


async def test_private_start_marks_user(env):
    feed, db, _ = env
    out = await feed(msg_update("/start", chat_id=PLAYER_ID, user_id=PLAYER_ID))
    assert "CoC War Bot" in out[0]
    assert await db.dm_recipients([PLAYER_ID]) == {PLAYER_ID}

    out = await feed(msg_update("привет", chat_id=PLAYER_ID, user_id=PLAYER_ID))
    assert "/menu" in out[0]
