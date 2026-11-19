"""Migrate account links from the old single-file bot (links.db) to the new database.

    python scripts/import_legacy.py path/to/links.db [data/clanwarden.db]

Old schema: links2(telegram_id TEXT, coc_tag TEXT). If a tag was linked by
several people, the first link wins — in the new version a tag has one owner.
Old subscriptions are not migrated: personal reminders are now on by default
for everyone who has sent /start to the bot.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clanwarden.coc.tags import normalize_tag  # noqa: E402
from clanwarden.db import Database  # noqa: E402


async def main(legacy_path: Path, new_path: Path) -> None:
    legacy = sqlite3.connect(legacy_path)
    try:
        rows = legacy.execute("SELECT telegram_id, coc_tag FROM links2 ORDER BY id").fetchall()
    except sqlite3.OperationalError:
        rows = legacy.execute("SELECT telegram_id, coc_tag FROM links").fetchall()
    legacy.close()

    db = Database(new_path)
    await db.connect()
    imported = skipped = 0
    for telegram_id, raw_tag in rows:
        tag = normalize_tag(raw_tag)
        if not tag or await db.get_link(tag):
            skipped += 1
            continue
        await db.save_link(tag, int(telegram_id), None, verified=False)
        imported += 1
    await db.close()
    print(f"Imported links: {imported}, skipped: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "data/clanwarden.db")))
