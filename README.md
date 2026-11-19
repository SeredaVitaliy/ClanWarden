# Clan Warden — Clash of Clans Telegram Bot

[![CI](https://github.com/SeredaVitaliy/ClanWarden/actions/workflows/ci.yml/badge.svg)](https://github.com/SeredaVitaliy/ClanWarden/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**[English](#english)** · **[Русский](#русский)**

Self-hosted Telegram bot for Clash of Clans clans: clan war & CWL tracking, attack reminders with mentions.
Self-hosted Telegram-бот для кланов Clash of Clans: войны, ЛВК, напоминания об атаках с упоминаниями.

---

## English

A self-hosted **Telegram bot for Clash of Clans** clans. Clan Warden tracks your **clan wars** and **Clan War League (CWL)** through the official Clash of Clans API. It posts to your clan's Telegram group when a war starts, sends a reminder with the list of players who haven't attacked yet (with clickable mentions), and posts the results. It can also remind each player privately.

You run it on your own server with a single command: `docker compose up -d`.

### Features

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

### What it looks like

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

### Installation

You need a server with a static IP (the cheapest VPS is enough) and Docker.

#### 1. Telegram bot token

Message [@BotFather](https://t.me/BotFather) → `/newbot` → save the token.

#### 2. Clash of Clans API key

1. Find your server's public IP: `curl -4 ifconfig.me`.
2. Sign up at [developer.clashofclans.com](https://developer.clashofclans.com) → *My Account* → *Create New Key*.
3. Put the server's IP in *Allowed IP addresses*.

> A key only works from the IPs listed in it. This is the most common reason the bot "can't see" a war.

#### 3. Run

```bash
git clone https://github.com/SeredaVitaliy/ClanWarden.git
cd ClanWarden
cp .env.example .env
nano .env          # set TELEGRAM_BOT_TOKEN and COC_API_TOKEN

docker compose run --rm bot python -m clanwarden check   # verify the tokens
docker compose up -d
docker compose logs -f                                   # logs
```

#### 4. Connect your clan

1. Add the bot to your clan's Telegram group.
2. A group admin sends `/setclan #CLAN_TAG`. The group language is taken from that admin's Telegram language; change it any time with `/language`.
3. If the group uses topics, send `/settopic` in the topic the bot should use.
4. Players link their accounts with `/link #PLAYER_TAG`. To get personal reminders, they also send `/start` to the bot in private.

The clan's **war log must be public** (Clan → Edit), otherwise the API doesn't return war data.

#### Updating

```bash
docker compose pull && docker compose up -d
```

#### Without Docker

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill it in
python -m clanwarden
```

For a long-running setup, wrap it in a systemd service.

### Commands

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

### Configuration

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | token from @BotFather, **required** |
| `COC_API_TOKEN` | — | key from developer.clashofclans.com, **required** |
| `POLL_INTERVAL_SECONDS` | `120` | how often to poll the API (minimum 30) |
| `DATABASE_PATH` | `data/clanwarden.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | log level |
| `COC_API_BASE_URL` | `https://api.clashofclans.com/v1` | point to a proxy if your server has no static IP |
| `CLAN_TAG`, `GROUP_CHAT_ID`, `GROUP_THREAD_ID` | — | single-clan quick setup without `/setclan` |

### Troubleshooting

**"the key doesn't allow this server's IP"** — the key was created for a different IP. Run `python -m clanwarden check`: the API response includes the IP the request came from. Create a key for that IP.

**"The clan's war log is private"** — a leader or co-leader makes it public in the clan settings.

**The bot doesn't message me privately** — Telegram doesn't let bots start a conversation. Send `/start` to the bot once.

**The bot doesn't reply in the group** — it may be bound to another topic; `/settings` shows where it works.

### Migrating from the old single-file version

The old version stored links in `links.db`. To import them:

```bash
python scripts/import_legacy.py links.db data/clanwarden.db
```

The group and clan from the old `.env` (`CLAN_TAG`, `GROUP_CHAT_ID`, `GROUP_THREAD_ID`) are picked up automatically on first start.

### Development

```bash
pip install -r requirements-dev.txt
pytest            # tests
ruff check .      # linter
ruff format .     # formatter
```

How the project is built and why: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

#### Adding a language

Copy `clanwarden/i18n/en.py` to e.g. `de.py`, translate the values, and register it in `clanwarden/i18n/__init__.py`. A test checks that every catalog has the same keys and placeholders as English.

### License

[MIT](LICENSE). This project is not affiliated with, endorsed, sponsored, or specifically approved by Supercell. Clash of Clans is a trademark of Supercell.

---

## Русский

Self-hosted **Telegram-бот для кланов Clash of Clans** (тг бот для клеш оф кленс). Clan Warden следит за **клановыми войнами (КВ)** и **Лигой войн кланов (ЛВК)** через официальный API игры. Он присылает в Telegram-группу клана старт войны, напоминание со списком тех, кто ещё не атаковал (с кликабельными упоминаниями), и итоги. Каждому игроку может напоминать лично.

Бот ставится на свой сервер одной командой: `docker compose up -d`.

### Возможности

- **Уведомления в группу:** соперник найден → война началась (с правилами клана) → «до конца N часов, не атаковали: …» → итоги.
- **Упоминания:** игроки привязывают аккаунт игры к Telegram, и бот зовёт именно тех, у кого остались атаки.
- **Личные напоминания:** если у твоего аккаунта осталась атака, бот напишет в личку.
- **ЛВК:** текущий раунд с правильным соперником и таблица группы с бонусом +10 звёзд за победу.
- **Несколько кланов на одном боте:** один запущенный бот обслуживает несколько групп, у каждой свой клан и свои настройки.
- **Темы (форумы):** бот работает только в выбранной теме и не мешает остальной переписке.
- **Подтверждение аккаунта:** чужой тег нельзя «занять», владение подтверждается API-токеном из настроек игры.
- **Надёжность:** журнал отправленных уведомлений хранится в базе, поэтому после перезапуска бот не дублирует «Война началась!» и не пропускает напоминание.
- **Понятные ошибки:** закрытый журнал войн, неверный IP ключа, техобслуживание — человек видит, что случилось и что делать.
- **Русский и английский:** язык выбирается для каждой группы и каждого пользователя, по умолчанию берётся язык Telegram.

### Как это выглядит

```
⏰ До конца войны 2ч 41м!
Legion vs Dark Empire · КВ, 15×15

❗ Ещё не атаковали:
4. Alex — осталось 2        ← имя кликабельное, Telegram пришлёт игроку уведомление
9. Snow — осталось 1
12. Maria — осталось 1

Без привязки к Telegram: 1. Привязать: /link #ТЕГ
```

```
🏆 Лига войн кланов · сезон 2026-11 · раунд 3/7

⚔️ День атак
Legion vs Raiders · ЛВК, раунд 3, 15×15
⏳ До конца войны: 11ч 5м

⭐ 21 : 18   💥 74.3% : 65.0%
🗡 Атаки: 9/15 : 8/15
```

### Установка

Понадобится сервер с постоянным IP (подойдёт самый дешёвый VPS) и Docker.

#### 1. Токен Telegram-бота

Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → сохраните токен.

#### 2. Ключ Clash of Clans API

1. Узнайте внешний IP сервера: `curl -4 ifconfig.me`.
2. Зарегистрируйтесь на [developer.clashofclans.com](https://developer.clashofclans.com) → *My Account* → *Create New Key*.
3. В поле *Allowed IP addresses* укажите IP сервера.

> Ключ работает только с указанных в нём IP. Это самая частая причина, почему бот «не видит» войну.

#### 3. Запуск

```bash
git clone https://github.com/SeredaVitaliy/ClanWarden.git
cd ClanWarden
cp .env.example .env
nano .env          # вставьте TELEGRAM_BOT_TOKEN и COC_API_TOKEN

docker compose run --rm bot python -m clanwarden check   # проверка токенов
docker compose up -d
docker compose logs -f                                   # логи
```

#### 4. Подключение к клану

1. Добавьте бота в Telegram-группу клана.
2. Админ группы пишет `/setclan #ТЕГ_КЛАНА`. Язык группы берётся из языка Telegram этого админа, сменить его можно в любой момент через `/language`.
3. Если в группе включены темы, напишите `/settopic` в теме, где должен работать бот.
4. Игроки привязывают аккаунты: `/link #ТЕГ_ИГРОКА`. Чтобы получать личные напоминания, нужно ещё один раз написать боту `/start` в личку.

Журнал войн клана должен быть **открыт** (клан → Настройки), иначе API не отдаёт данные о войне.

#### Обновление

```bash
docker compose pull && docker compose up -d
```

#### Без Docker

Нужен Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить
python -m clanwarden
```

Для постоянной работы оформите запуск как systemd-сервис.

### Команды

| Команда | Где | Что делает |
|---|---|---|
| `/war` | везде | текущая война или раунд ЛВК: счёт, атаки, оставшееся время |
| `/missed` | везде | кто ещё не провёл атаки |
| `/cwl` · `/cwltable` | везде | раунд ЛВК · таблица группы |
| `/me` | везде | мои аккаунты и мои атаки в текущей войне |
| `/link #ТЕГ [ТОКЕН]` | везде | привязать аккаунт (с токеном — подтверждённо) |
| `/unlink [#ТЕГ]` | везде | отвязать аккаунт |
| `/notify` | везде | личные напоминания вкл/выкл |
| `/language` | везде | язык бота (в группе — только админы) |
| `/menu` | везде | всё то же самое кнопками |
| `/setclan #ТЕГ` | группа, админ | привязать клан к группе |
| `/settopic` · `/unsettopic` | группа, админ | работать только в этой теме / во всём чате |
| `/settings` | группа, админ | какие уведомления слать, за сколько часов напоминать, упоминания, автоудаление ответов |
| `/setrules текст` | группа, админ | правила клана, бот покажет их в начале войны |
| `/checklinks` | группа, админ | кто из клана не привязал аккаунт |

В личке `/war`, `/missed` и `/cwl` работают для клана вашего привязанного аккаунта, либо укажите тег: `/war #ТЕГ`.

### Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | токен от @BotFather, **обязательно** |
| `COC_API_TOKEN` | — | ключ с developer.clashofclans.com, **обязательно** |
| `POLL_INTERVAL_SECONDS` | `120` | как часто опрашивать API (минимум 30) |
| `DATABASE_PATH` | `data/clanwarden.db` | путь к SQLite-базе |
| `LOG_LEVEL` | `INFO` | уровень логов |
| `COC_API_BASE_URL` | `https://api.clashofclans.com/v1` | можно указать прокси, если у сервера нет постоянного IP |
| `CLAN_TAG`, `GROUP_CHAT_ID`, `GROUP_THREAD_ID` | — | быстрая настройка одного клана без `/setclan` |

### Частые проблемы

**«ключ не разрешён для IP этого сервера»** — ключ создан для другого IP. Запустите `python -m clanwarden check`: в ответе API будет IP, с которого пришёл запрос. Создайте ключ для этого IP.

**«Журнал войн клана закрыт»** — глава или соруководитель открывает его в настройках клана.

**Бот не пишет в личку** — Telegram не разрешает ботам писать первыми. Нужно один раз отправить боту `/start`.

**Бот не отвечает в группе** — возможно, он привязан к другой теме; `/settings` покажет, где он работает.

### Переход со старой однофайловой версии

Старая версия хранила привязки в `links.db`. Перенести их:

```bash
python scripts/import_legacy.py links.db data/clanwarden.db
```

Группу и клан из старого `.env` (`CLAN_TAG`, `GROUP_CHAT_ID`, `GROUP_THREAD_ID`) новая версия подхватит сама при первом запуске.

### Разработка

```bash
pip install -r requirements-dev.txt
pytest            # тесты
ruff check .      # линтер
ruff format .     # форматирование
```

Как устроен проект и почему именно так: [docs/ARCHITECTURE.ru.md](docs/ARCHITECTURE.ru.md).

#### Добавить язык

Скопируйте `clanwarden/i18n/en.py`, например в `de.py`, переведите значения и зарегистрируйте файл в `clanwarden/i18n/__init__.py`. Тест проверит, что у всех каталогов одинаковые ключи и плейсхолдеры.

### Лицензия

[MIT](LICENSE). Проект не связан с Supercell, не одобрен и не спонсируется ею. Clash of Clans — торговая марка Supercell.
