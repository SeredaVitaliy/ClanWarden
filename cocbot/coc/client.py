"""Асинхронный клиент Clash of Clans API.

Что он берёт на себя:
- превращает HTTP-ошибки в понятные исключения (закрытый журнал войн,
  неверный IP ключа, техобслуживание), чтобы бот мог ответить человеку
  по-человечески, а не "что-то пошло не так";
- кэширует ответы на короткое время: несколько команд подряд или несколько
  групп с одним кланом не тратят лимиты API;
- кэширует навсегда завершённые войны ЛВК — они уже не изменятся.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from cocbot.coc.models import Clan, CwlGroup, Player, War, WarState
from cocbot.coc.tags import encode_tag

log = logging.getLogger(__name__)


class CocApiError(Exception):
    def __init__(self, status: int, reason: str = "", message: str = "") -> None:
        self.status = status
        self.reason = reason
        self.message = message
        super().__init__(f"CoC API {status} {reason}: {message}".strip())


class NotFound(CocApiError):
    """Клан/игрок не существует (или клан не участвует в ЛВК)."""


class AccessDenied(CocApiError):
    """Чаще всего — закрытый журнал войн клана."""


class InvalidIp(CocApiError):
    """Ключ API не разрешён для IP этого сервера. Это ошибка настройки, а не пользователя."""


class Maintenance(CocApiError):
    """Игра на техобслуживании."""


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
        # Одинаковые одновременные запросы склеиваем в один.
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
            # Исключение уже проброшено вызывающему; глушим "never retrieved".
            future.exception()
            raise
        finally:
            self._inflight.pop(path, None)

    # --- публичные методы ---

    async def ping(self) -> None:
        """Самый лёгкий запрос, требующий авторизации: проверка ключа и IP."""
        await self._request("GET", "/locations?limit=1")

    async def get_clan(self, tag: str) -> Clan:
        return Clan.from_api(await self._get(f"/clans/{encode_tag(tag)}", ttl=300))

    async def get_player(self, tag: str) -> Player:
        return Player.from_api(await self._get(f"/players/{encode_tag(tag)}", ttl=300))

    async def get_current_war(self, clan_tag: str) -> War:
        """Обычная война. В API наш клан всегда в поле `clan`."""
        data = await self._get(f"/clans/{encode_tag(clan_tag)}/currentwar")
        return War.from_api(data)

    async def get_league_group(self, clan_tag: str) -> CwlGroup | None:
        """Группа ЛВК или None, если клан сейчас в ЛВК не участвует."""
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
        """Проверка владения аккаунтом: токен игрок берёт в настройках игры.

        Токен одноразовый и живёт несколько минут, поэтому не кэшируем.
        """
        data = await self._request(
            "POST", f"/players/{encode_tag(player_tag)}/verifytoken", json={"token": token}
        )
        return data.get("status") == "ok"
