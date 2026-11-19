# Architecture

**English** · [Русский](ARCHITECTURE.ru.md)

## Layout

```
clanwarden/
├── __main__.py          entry point: `python -m clanwarden [run|check]`
├── app.py               wiring: dependencies, routers, background task
├── config.py            reading and validating environment variables
├── db.py                SQLite: schema, migrations, queries
├── texts.py             message rendering (HTML) from catalog strings
├── i18n/                string catalogs: en.py, ru.py + translator
├── coc/
│   ├── client.py        CoC API HTTP client: errors, caching
│   ├── models.py        dataclass models: War, WarMember, CwlGroup…
│   └── tags.py          tag normalization
├── services/
│   ├── wars.py          war and CWL logic (finding our war, standings)
│   ├── notifications.py pure function: which notifications are due
│   └── notifier.py      background loop: poll API → plan → send → journal
└── bot/
    ├── middlewares.py   group settings and translator for handlers + topic filter
    ├── helpers.py       admin checks, clan resolution, API error messages
    ├── keyboards.py     inline keyboards and callback data
    ├── views.py         reply builders shared by commands and buttons
    └── handlers/        commands: war, accounts, admin, common
```

Dependencies point downwards: `bot` → `services` → `coc`, `db`. The `coc` and `services` packages know nothing about Telegram, so they're tested without it.

## Key decisions

### Notifications: "state + journal" instead of timers

The obvious approach is a timer: "send the reminder in N hours". It breaks when the bot restarts, when the server is down, and when the bot joins a group in the middle of a war.

Instead, every couple of minutes the bot looks at the current state of each war and asks a pure function, `plan_events(war, now, settings, already_sent)`, what is due. Whatever gets sent is recorded in the `sent_events` table keyed by *(chat, war, event)*. As a result:

- a restart never duplicates anything — the journal lives in the database;
- if the server was down, a reminder goes out right after it's back, as long as its window is still open;
- stale events have a grace period: if the bot joins 10 hours into a war, it won't post "The war has started!".

`plan_events` does no I/O, so every edge case is covered by plain unit tests.

### War identity

The API doesn't give regular wars an ID. The key is built from both clan tags (sorted, so it doesn't depend on the side) and the preparation start time. CWL wars have a `warTag`, which is used directly.

### CWL: finding our war

`/leaguegroup` returns 8 clans and 4 wars per round but doesn't say which one is ours. In a CWL war, our clan can be in either the `clan` or the `opponent` field. The original version simply took the first ongoing war of the group, which could belong to other clans.

Now the service walks the rounds from the latest, finds the war that contains our tag, and orients it (`War.oriented`) so our clan is always in `clan`. The found `warTag` is cached per season and round, so the next poll needs one request instead of four. Finished CWL wars are cached forever since they can't change.

### One poll per clan

If a clan is connected to two groups, the API is polled once and the result is delivered to both. On top of that, the client has a short response cache and merges identical concurrent requests.

### Account links

A tag has exactly one owner (`PRIMARY KEY (player_tag)`), otherwise mentions would ping the wrong people. A free tag can be linked without verification. Taking over a tag that's already linked requires the one-time API token from the game settings, checked via `POST /players/{tag}/verifytoken`.

### Internationalization

All user-facing text lives in `clanwarden/i18n/en.py` and `ru.py` under keys. The code contains no UI strings — it calls `t("key", **params)`. A middleware resolves the language and injects the translator `t` into every handler:

- in a group — the language set with `/language`; on first setup (`/setclan`) the admin's Telegram language is adopted;
- in private chat — the user's chosen language, otherwise their Telegram language.

Background notifications use the group's language; personal reminders use the player's. A missing key falls back to English, so a partial translation never breaks the bot, and a test asserts that all catalogs share the same keys and placeholders. Telegram's "/" command menu is registered in every language too (`set_my_commands` with `language_code`).

### Why SQLite

The bot ships as a single container for a small VPS and writes a few dozen rows a minute. A separate database server would only make installation harder. Migrations are versioned with `PRAGMA user_version`.

### Why HTML instead of Markdown

Player names contain `*`, `_` and backticks, which break Markdown entities (the original version had to resend messages without formatting because of this). With HTML only `<`, `>` and `&` need escaping.

### No global state

The API client, database and services are created in `app.py` and stored in the aiogram `Dispatcher`, which passes them to handlers by argument name (`db`, `coc`, `wars`). That makes them trivial to replace with stubs in tests.

## Tests

| File | What it covers |
|---|---|
| `test_models.py` | API parsing, tags, war orientation, results |
| `test_notifications.py` | notification windows and grace periods |
| `test_wars_service.py` | finding our CWL war, warTag caching, standings with bonuses |
| `test_client.py` | HTTP client against a fake server: errors, caching, verifytoken |
| `test_texts.py` | HTML escaping, mentions, localization, catalog key parity |
| `test_db.py` | migrations, links, journal |
| `test_notifier.py` | notification loop: no duplicates, mentions, DMs, topics |
| `test_bot_smoke.py` | end-to-end aiogram run on fake updates: permissions, topics, buttons, language switching |

## Possible next steps

- Per-player war statistics (average stars, missed attacks) and an end-of-season summary.
- More languages — just add a catalog file.
- Automatic API key rotation via the developer account login, for servers with a dynamic IP.
- Webhooks instead of long polling for large installations.
