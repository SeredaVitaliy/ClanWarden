# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-11-19

First public release. The single-file bot for one clan was rewritten into **Clan Warden**, a self-hosted bot any clan can run.

### Added
- Group notifications: opponent found, war started (with clan rules), reminder N hours before the end with mentions of players who haven't attacked, war results.
- Personal reminders in private chat for players with attacks left.
- Clan War League: current round with the correct opponent, group standings with the +10 stars win bonus.
- `/stats`: per-player stars, average per attack, destruction and missed attacks over recent wars (`/stats 20`), a CWL season (`/stats cwl`) or for one player (`/stats #TAG`). The bot keeps its own war history for this.
- Multiple groups and clans per bot instance, per-group settings (`/settings`), forum topic support (`/settopic`), clan rules (`/setrules`), link audit (`/checklinks`).
- Account linking with ownership verification through the in-game API token.
- English and Russian interface: per-group and per-user language, Telegram language auto-detection, `/language`.
- Docker image, `docker compose` setup, `python -m clanwarden check` to verify tokens.
- CI: ruff and pytest on Python 3.11 and 3.13, image published to GitHub Container Registry.
- Script to import links from the old version's `links.db`.

### Fixed (compared to the old single-file bot)
- CWL could show another clan's war: the bot took the first ongoing war of the group.
- Results of CWL rounds were never reported, because a round ends at the same moment the next one starts.
- The "war started" notification never fired.
- Restarts re-sent notifications: the "already sent" flags lived in memory. They are now journaled in the database.
- Markdown broke on player names with special characters; messages now use escaped HTML.

[1.0.0]: https://github.com/SeredaVitaliy/ClanWarden/releases/tag/v1.0.0
