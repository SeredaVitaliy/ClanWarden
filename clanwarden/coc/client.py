"""Async Clash of Clans API client.

What it takes care of:
- turns HTTP errors into meaningful exceptions (private war log, key not
  allowed for this IP, maintenance) so the bot can tell people what's wrong
  instead of "something went wrong";
- caches responses briefly: several commands in a row, or several groups
  following the same clan, don't burn through API limits;
- caches finished CWL wars forever — they can't change anymore.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from clanwarden.coc.models import Clan, CwlGroup, Player, War, WarState
from clanwarden.coc.tags import encode_tag

log = logging.getLogger(__name__)


class CocApiError(Exception):
    def __init__(self, status: int, reason: str = "", message: str = "") -> None:
        self.status = status
        self.reason = reason
        self.message = message
        super().__init__(f"CoC API {status} {reason}: {message}".strip())


class NotFound(CocApiError):
    """Clan/player doesn't exist (or the clan isn't in CWL)."""


class AccessDenied(CocApiError):
    """Usually the clan's war log is private."""


class InvalidIp(CocApiError):
    """The API key doesn't allow this server's IP. A setup error, not a user error."""


class Maintenance(CocApiError):
    """The game is under maintenance."""


class RateLimited(CocApiError):
    pass


def _error_for(status: int, payload: dict[str, Any]) -> CocApiError:
    reason = str(payload.get("reason", ""))
    message = str(payload.get("message", ""))
    if status == 404:
        return NotFound(status, reason, message)
    if status == 403:
        if reason == "accessDenied.invalidIp":
            return InvalidIp(status, reason, message)
        return AccessDenied(status, reason, message)
    if status == 503:
        return Maintenance(status, reason, message)
    if status == 429:
        return RateLimited(status, reason, message)
    return CocApiError(status, reason, message)


class CocClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.clashofclans.com/v1",
        *,
        cache_ttl: float = 60.0,
        timeout: float = 15.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._ended_cwl_wars: dict[str, War] = {}
        # Identical concurrent requests are merged into one.
        self._inflight: dict[str, asyncio.Future] = {}

    async def __aenter__(self) -> CocClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            )
        return self._session

    async def _request(self, method: str, path: str, json: dict | None = None) -> Any:
        url = self._base_url + path
        async with self._get_session().request(method, url, json=json) as resp:
            try:
                payload = await resp.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                payload = {}
            if resp.status != 200:
                raise _error_for(resp.status, payload if isinstance(payload, dict) else {})
            return payload

    async def _get(self, path: str, *, ttl: float | None = None) -> Any:
        ttl = self._cache_ttl if ttl is None else ttl
        cached = self._cache.get(path)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        if path in self._inflight:
            return await asyncio.shield(self._inflight[path])

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[path] = future
        try:
            data = await self._request("GET", path)
            self._cache[path] = (time.monotonic() + ttl, data)
            future.set_result(data)
            return data
        except Exception as exc:
            future.set_exception(exc)
            # The caller already got the exception; silence "exception was never retrieved".
            future.exception()
            raise
        finally:
            self._inflight.pop(path, None)

    # --- public methods ---

    async def ping(self) -> None:
        """The cheapest authorized request: checks the key and the IP."""
        await self._request("GET", "/locations?limit=1")

    async def get_clan(self, tag: str) -> Clan:
        return Clan.from_api(await self._get(f"/clans/{encode_tag(tag)}", ttl=300))

    async def get_player(self, tag: str) -> Player:
        return Player.from_api(await self._get(f"/players/{encode_tag(tag)}", ttl=300))

    async def get_current_war(self, clan_tag: str) -> War:
        """Regular war. The API always puts our clan in `clan`."""
        data = await self._get(f"/clans/{encode_tag(clan_tag)}/currentwar")
        return War.from_api(data)

    async def get_league_group(self, clan_tag: str) -> CwlGroup | None:
        """The CWL group, or None if the clan isn't in CWL right now."""
        try:
            data = await self._get(f"/clans/{encode_tag(clan_tag)}/currentwar/leaguegroup")
        except NotFound:
            return None
        return CwlGroup.from_api(data)

    async def get_cwl_war(self, war_tag: str) -> War:
        if war_tag in self._ended_cwl_wars:
            return self._ended_cwl_wars[war_tag]
        data = await self._get(f"/clanwarleagues/wars/{encode_tag(war_tag)}")
        war = War.from_api(data, is_cwl=True, war_tag=war_tag)
        if war.state is WarState.ENDED:
            self._ended_cwl_wars[war_tag] = war
        return war

    async def verify_player_token(self, player_tag: str, token: str) -> bool:
        """Account ownership check: players get the token from the game settings.

        Tokens are single-use and expire in minutes, so this is never cached.
        """
        data = await self._request(
            "POST", f"/players/{encode_tag(player_tag)}/verifytoken", json={"token": token}
        )
        return data.get("status") == "ok"
