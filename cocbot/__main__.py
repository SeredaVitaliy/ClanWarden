"""Точка входа.

python -m cocbot          — запустить бота
python -m cocbot check    — проверить токены и доступ к API (удобно после установки)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys

from cocbot.config import ConfigError, load_settings


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # aiogram логирует каждый апдейт на INFO — это шумно для продакшена.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def _check(settings) -> int:
    from aiogram import Bot

    from cocbot.coc.client import CocApiError, CocClient, InvalidIp

    ok = True
    bot = Bot(settings.telegram_token)
    try:
        me = await bot.get_me()
        print(f"✅ Telegram: бот @{me.username}")
    except Exception as exc:
        print(f"❌ Telegram: {exc}")
        ok = False
    finally:
        await bot.session.close()

    async with CocClient(settings.coc_token, settings.coc_base_url) as coc:
        try:
            await coc.ping()
            print("✅ Clash of Clans API: ключ работает")
            if settings.bootstrap_clan_tag:
                clan = await coc.get_clan(settings.bootstrap_clan_tag)
                log_state = "открыт" if clan.war_log_public else "ЗАКРЫТ — бот не увидит войны"
                print(f"✅ Клан {clan.name} {clan.tag}: журнал войн {log_state}")
        except InvalidIp as exc:
            print(f"❌ Clash of Clans API: ключ не разрешён для IP этого сервера.\n   {exc.message}")
            print("   Создайте ключ на https://developer.clashofclans.com с IP из сообщения выше.")
            ok = False
        except CocApiError as exc:
            print(f"❌ Clash of Clans API: {exc}")
            ok = False
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="cocbot", description="CoC War Bot")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "check"])
    args = parser.parse_args()

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        sys.exit(2)

    _setup_logging(settings.log_level)

    if args.command == "check":
        sys.exit(asyncio.run(_check(settings)))

    from cocbot.app import run

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(settings))


if __name__ == "__main__":
    main()
