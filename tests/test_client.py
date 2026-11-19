"""Клиент против локального фейкового сервера: коды ошибок и кэш."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from cocbot.coc.client import AccessDenied, CocClient, InvalidIp, NotFound
from tests.factories import war_json


@pytest.fixture
async def api():
    calls: dict[str, int] = {}

    async def handler(request: web.Request) -> web.Response:
        path = request.path
        calls[path] = calls.get(path, 0) + 1
        assert request.headers["Authorization"] == "Bearer test-token"
        if path == "/v1/clans/#OURS/currentwar":
            return web.json_response(war_json())
        if path == "/v1/clans/#PRIVATE/currentwar":
            return web.json_response({"reason": "accessDenied", "message": "private"}, status=403)
        if path == "/v1/clans/#BADIP/currentwar":
            return web.json_response(
                {"reason": "accessDenied.invalidIp", "message": "Invalid IP 1.2.3.4"}, status=403
            )
        if path == "/v1/clans/#OURS/currentwar/leaguegroup":
            return web.json_response({"reason": "notFound"}, status=404)
        if path == "/v1/players/#P1/verifytoken":
            body = await request.json()
            return web.json_response({"status": "ok" if body["token"] == "good" else "invalid"})
        return web.json_response({"reason": "notFound"}, status=404)

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    server = TestServer(app)
    await server.start_server()
    client = CocClient("test-token", str(server.make_url("/v1")))
    yield client, calls
    await client.close()
    await server.close()


async def test_current_war_and_cache(api):
    client, calls = api
    war = await client.get_current_war("#OURS")
    await client.get_current_war("#OURS")
    assert war.clan.name == "Наши"
    assert calls["/v1/clans/#OURS/currentwar"] == 1  # второй раз — из кэша


async def test_error_mapping(api):
    client, _ = api
    with pytest.raises(AccessDenied):
        await client.get_current_war("#PRIVATE")
    with pytest.raises(InvalidIp) as exc:
        await client.get_current_war("#BADIP")
    assert "1.2.3.4" in exc.value.message
    with pytest.raises(NotFound):
        await client.get_player("#NOPE")


async def test_not_in_cwl_returns_none(api):
    client, _ = api
    assert await client.get_league_group("#OURS") is None


async def test_verify_token(api):
    client, _ = api
    assert await client.verify_player_token("#P1", "good") is True
    assert await client.verify_player_token("#P1", "bad") is False
