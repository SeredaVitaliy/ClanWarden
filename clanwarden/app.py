"""Application wiring: dependencies, routers, background task."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from clanwarden.bot.handlers import accounts, admin, common, war
from clanwarden.bot.middlewares import ChatContextMiddleware
from clanwarden.coc.client import CocClient
from clanwarden.config import Settings
from clanwarden.db import Database
from clanwarden.i18n import CATALOGS, DEFAULT_LANGUAGE, Translator
from clanwarden.services.notifier import Notifier
from clanwarden.services.wars import WarService

log = logging.getLogger(__name__)

PRIVATE_COMMANDS = ("menu", "me", "war", "missed", "cwl", "link", "unlink", "notify", "language", "help")
GROUP_COMMANDS = ("war", "missed", "cwl", "cwltable", "me", "link", "menu", "settings", "language", "help")


def build_dispatcher(db: Database | None, coc: CocClient | None, wars: WarService | None) -> Dispatcher:
    # Dependencies live in the dispatcher; aiogram passes them to handlers by
    # argument name (db, coc, wars). No module-level globals.
    dp = Dispatcher(db=db, coc=coc, wars=wars)
    middleware = ChatContextMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    dp.include_routers(common.router, war.router, accounts.router, admin.router, common.fallback_router)
    return dp


async def register_commands(bot: Bot) -> None:
    """Publish the command list shown in Telegram's "/" menu, in every supported language."""
    for language in CATALOGS:
        t = Translator(language)
        # Commands without language_code are the fallback for all other languages.
        code = None if language == DEFAULT_LANGUAGE else language
        for names, scope in (
            (PRIVATE_COMMANDS, BotCommandScopeAllPrivateChats()),
            (GROUP_COMMANDS, BotCommandScopeAllGroupChats()),
        ):
            commands = [BotCommand(command=name, description=t(f"cmd_{name}")) for name in names]
            await bot.set_my_commands(commands, scope=scope, language_code=code)


async def bootstrap_chat(db: Database, settings: Settings) -> None:
    """Single-clan quick setup: connect a group to a clan from environment variables."""
    if settings.bootstrap_chat_id and settings.bootstrap_clan_tag:
        chat = await db.get_chat(settings.bootstrap_chat_id)
        if not chat or not chat.clan_tag:
            await db.set_chat_clan(settings.bootstrap_chat_id, settings.bootstrap_clan_tag)
            if settings.bootstrap_thread_id:
                await db.set_chat_thread(settings.bootstrap_chat_id, settings.bootstrap_thread_id)
            log.info(
                "Group %s connected to clan %s from environment variables",
                settings.bootstrap_chat_id,
                settings.bootstrap_clan_tag,
            )


async def run(settings: Settings) -> None:
    db = Database(settings.database_path)
    await db.connect()
    await bootstrap_chat(db, settings)

    coc = CocClient(settings.coc_token, settings.coc_base_url)
    wars = WarService(coc)
    bot = Bot(settings.telegram_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(db, coc, wars)

    me = await bot.get_me()
    log.info("Running as @%s", me.username)
    await register_commands(bot)

    notifier = Notifier(bot, db, wars, settings.poll_interval)
    notifier_task = asyncio.create_task(notifier.run(), name="notifier")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        notifier_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await notifier_task
        await coc.close()
        await bot.session.close()
        await db.close()
