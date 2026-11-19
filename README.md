# Clan Warden — Clash of Clans Telegram Bot

[![CI](https://github.com/SeredaVitaliy/clan-warden/actions/workflows/ci.yml/badge.svg)](https://github.com/SeredaVitaliy/clan-warden/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**English** · [Русский](README.ru.md)

A self-hosted **Telegram bot for Clash of Clans** clans. Clan Warden tracks your **clan wars** and **Clan War League (CWL)** through the official Clash of Clans API. It posts to your clan's Telegram group when a war starts, sends a reminder with the list of players who haven't attacked yet (with clickable mentions), and posts the results. It can also remind each player privately.

You run it on your own server with a single command: `docker compose up -d`.

## Features

- **Group notifications:** opponent found → war started (with your clan rules) → "N hours left, these players haven't attacked: …" → results.
- **Mentions:** players link their game account to Telegram, so the bot pings exactly the people who still have attacks left.
- **Personal reminders:** if your account still has an attack, the bot messages you privately.
- **Clan War League:** the current round with the correct opponent, plus group standings with the +10 stars war-win bonus.
- **Many clans, one bot:** a single running bot can serve several groups, each with its own clan and settings.
- **Forum topics:** the bot can be limited to one topic so it doesn't get in the way of other conversations.
- **Account verification:** nobody can claim someone else's tag; ownership is proven with the API token from the game settings.
- **Reliable:** delivered notifications are journaled in the database, so a restart never duplicates "The war has started!" and never misses a reminder.
- **Clear errors:** a private war log, a wrong API key IP, or game maintenance — people see what happened and what to do.
- **English and Russian:** each group and each user picks a language; the bot defaults to the user's Telegram language.

## What it looks like

```
⏰ 2h 41m left in the war!
Legion vs Dark Empire · War, 15×15

❗ Haven't attacked yet:
4. Alex — 2 left        ← clickable name, Telegram notifies the player
9. Snow — 1 left
12. Maria — 1 left

Not linked to Telegram: 1. Link with /link #TAG
```

```
🏆 Clan War League · season 2026-11 · round 3/7

⚔️ Battle day
Legion vs Raiders · CWL, round 3, 15×15
⏳ War ends in: 11h 5m

⭐ 21 : 18   💥 74.3% : 65.0%
🗡 Attacks: 9/15 : 8/15
```

## Installation

You need a server with a static IP (the cheapest VPS is enough) and Docker.

### 1. Telegram bot token

Message [@BotFather](https://t.me/BotFather) → `/newbot` → save the token.

### 2. Clash of Clans API key

1. Find your server's public IP: `curl -4 ifconfig.me`.
2. Sign up at [developer.clashofclans.com](https://developer.clashofclans.com) → *My Account* → *Create New Key*.
3. Put the server's IP in *Allowed IP addresses*.

> A key only works from the IPs listed in it. This is the most common reason the bot "can't see" a war.

### 3. Run

```bash
git clone https://github.com/SeredaVitaliy/clan-warden.git
cd clan-warden
cp .env.example .env
nano .env          # set TELEGRAM_BOT_TOKEN and COC_API_TOKEN

docker compose run --rm bot python -m clanwarden check   # verify the tokens
docker compose up -d
docker compose logs -f                                   # logs
```

### 4. Connect your clan

1. Add the bot to your clan's Telegram group.
2. A group admin sends `/setclan #CLAN_TAG`. The group language is taken from that admin's Telegram language; change it any time with `/language`.
3. If the group uses topics, send `/settopic` in the topic the bot should use.
4. Players link their accounts with `/link #PLAYER_TAG`. To get personal reminders, they also send `/start` to the bot in private.

The clan's **war log must be public** (Clan → Edit), otherwise the API doesn't return war data.

### Updating

```bash
docker compose pull && docker compose up -d
```

### Without Docker

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill it in
python -m clanwarden
```

For a long-running setup, wrap it in a systemd service.

## Commands

| Command | Where | What it does |
|---|---|---|
| `/war` | anywhere | current war or CWL round: score, attacks, time left |
| `/missed` | anywhere | who hasn't used their attacks yet |
| `/cwl` · `/cwltable` | anywhere | CWL round · group standings |
| `/me` | anywhere | my accounts and my attacks in the current war |
| `/link #TAG [TOKEN]` | anywhere | link an account (with a token, verified) |
| `/unlink [#TAG]` | anywhere | unlink an account |
| `/notify` | anywhere | personal reminders on/off |
| `/language` | anywhere | bot language (for a group: admins only) |
| `/menu` | anywhere | everything above as buttons |
| `/setclan #TAG` | group, admin | connect a clan to the group |
| `/settopic` · `/unsettopic` | group, admin | work only in this topic / in the whole chat |
| `/settings` | group, admin | which notifications to send, reminder timing, mentions, auto-delete of replies |
| `/setrules text` | group, admin | clan rules shown when a war starts |
| `/checklinks` | group, admin | clan members who haven't linked their account |

In private chat, `/war`, `/missed` and `/cwl` use the clan of your linked account, or pass a tag: `/war #TAG`.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | token from @BotFather, **required** |
| `COC_API_TOKEN` | — | key from developer.clashofclans.com, **required** |
| `POLL_INTERVAL_SECONDS` | `120` | how often to poll the API (minimum 30) |
| `DATABASE_PATH` | `data/clanwarden.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | log level |
| `COC_API_BASE_URL` | `https://api.clashofclans.com/v1` | point to a proxy if your server has no static IP |
| `CLAN_TAG`, `GROUP_CHAT_ID`, `GROUP_THREAD_ID` | — | single-clan quick setup without `/setclan` |

## Troubleshooting

**"the key doesn't allow this server's IP"** — the key was created for a different IP. Run `python -m clanwarden check`: the API response includes the IP the request came from. Create a key for that IP.

**"The clan's war log is private"** — a leader or co-leader makes it public in the clan settings.

**The bot doesn't message me privately** — Telegram doesn't let bots start a conversation. Send `/start` to the bot once.

**The bot doesn't reply in the group** — it may be bound to another topic; `/settings` shows where it works.

## Migrating from the old single-file version

The old version stored links in `links.db`. To import them:

```bash
python scripts/import_legacy.py links.db data/clanwarden.db
```

The group and clan from the old `.env` (`CLAN_TAG`, `GROUP_CHAT_ID`, `GROUP_THREAD_ID`) are picked up automatically on first start.

## Development

```bash
pip install -r requirements-dev.txt
pytest            # tests
ruff check .      # linter
ruff format .     # formatter
```

How the project is built and why: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Adding a language

Copy `clanwarden/i18n/en.py` to e.g. `de.py`, translate the values, and register it in `clanwarden/i18n/__init__.py`. A test checks that every catalog has the same keys and placeholders as English.

## License

[MIT](LICENSE). This project is not affiliated with, endorsed, sponsored, or specifically approved by Supercell. Clash of Clans is a trademark of Supercell.
