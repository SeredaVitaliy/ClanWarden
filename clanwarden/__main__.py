"""Entry point.

python -m clanwarden          — run the bot
python -m clanwarden check    — verify tokens and API access (handy right after installing)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys

from clanwarden.config import ConfigError, Settings, load_settings


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # aiogram logs every update at INFO, which is too noisy for production.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def _check(settings: Settings) -> int:
    from aiogram import Bot

    from clanwarden.coc.client import CocApiError, CocClient, InvalidIp

    ok = True
    bot = Bot(settings.telegram_token)
    try:
        me = await bot.get_me()
        print(f"✅ Telegram: bot @{me.username}")
    except Exception as exc:
        print(f"❌ Telegram: {exc}")
        ok = False
    finally:
        await bot.session.close()

    async with CocClient(settings.coc_token, settings.coc_base_url) as coc:
        try:
            await coc.ping()
            print("✅ Clash of Clans API: key works")
            if settings.bootstrap_clan_tag:
                clan = await coc.get_clan(settings.bootstrap_clan_tag)
                war_log = "public" if clan.war_log_public else "PRIVATE — the bot won't see wars"
                print(f"✅ Clan {clan.name} {clan.tag}: war log is {war_log}")
        except InvalidIp as exc:
            print(f"❌ Clash of Clans API: the key doesn't allow this server's IP.\n   {exc.message}")
            print("   Create a key at https://developer.clashofclans.com with the IP shown above.")
            ok = False
        except CocApiError as exc:
            print(f"❌ Clash of Clans API: {exc}")
            ok = False
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="clanwarden", description="Clan Warden — Clash of Clans Telegram bot"
    )
    parser.add_argument("command", nargs="?", default="run", choices=["run", "check"])
    args = parser.parse_args()

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    _setup_logging(settings.log_level)

    if args.command == "check":
        sys.exit(asyncio.run(_check(settings)))

    from clanwarden.app import run

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(settings))


if __name__ == "__main__":
    main()
