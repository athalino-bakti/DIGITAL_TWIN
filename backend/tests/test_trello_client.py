"""DIG-119: konektor Trello API dengan server Trello tiruan (httpx.MockTransport)."""

import json

import httpx
import pytest

from app.integrations.trello import fetch_board
from app.integrations.trello.client import (
    PAGE_LIMIT,
    TrelloAuthError,
    TrelloClient,
    TrelloDisabledError,
    TrelloError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    client_from_settings,
)
from app.integrations.trello.config import TrelloSettings

KEY = "kunci-api-uji"
TOKEN = "token-rahasia-uji-0123456789"
BOARD_ID = "5f1a2b3c4d5e6f7a8b9c0d1e"
SHORT_LINK = "AbCd1234"


def make_actions(count: int) -> list[dict]:
    # ID action Trello naik seiring waktu; API mengembalikan yang terbaru lebih dulu.
    return [
        {
            "id": f"{i:024x}",
            "type": "updateCard",
            "date": f"2026-10-{1 + i % 28:02d}T08:00:00.000Z",
            "data": {"listBefore": {"name": "To Do"}, "listAfter": {"name": "Doing"}},
            "memberCreator": {"fullName": "Anggota", "username": "anggota"},
        }
        for i in range(count, 0, -1)
    ]


class FakeTrello:
    """Server Trello tiruan yang mencatat setiap request."""

    def __init__(self, actions: list[dict] | None = None, script: list[int] | None = None):
        self.actions = actions if actions is not None else make_actions(3)
        self.script = list(script or [])  # status yang dikembalikan lebih dulu, mis. [429, 500]
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.script:
            status = self.script.pop(0)
            headers = {"retry-after": "3"} if status == 429 else {}
            return httpx.Response(status, json={"error": "X"}, headers=headers)

        path = request.url.path.removeprefix("/1")
        if path in (f"/boards/{BOARD_ID}", f"/boards/{SHORT_LINK}"):
            return httpx.Response(
                200, json={"id": BOARD_ID, "name": "Papan PuTI", "shortLink": SHORT_LINK}
            )
        if path == f"/boards/{BOARD_ID}/lists":
            return httpx.Response(200, json=[{"id": "l1", "name": "To Do"}])
        if path == f"/boards/{BOARD_ID}/cards":
            return httpx.Response(200, json=[{"id": "c1", "name": "Kartu", "idList": "l1"}])
        if path == f"/boards/{BOARD_ID}/members":
            return httpx.Response(200, json=[{"id": "m1", "fullName": "Anggota"}])
        if path == f"/boards/{BOARD_ID}/labels":
            return httpx.Response(200, json=[{"id": "lb1", "name": "BE", "color": "green"}])
        if path == f"/boards/{BOARD_ID}/actions":
            limit = int(request.url.params["limit"])
            before = request.url.params.get("before")
            remaining = [a for a in self.actions if before is None or a["id"] < before]
            return httpx.Response(200, json=remaining[:limit])
        return httpx.Response(404, text="not found")

    def action_calls(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith("/actions")]


def make_client(fake: FakeTrello, sleeps: list[float] | None = None) -> TrelloClient:
    sleeps = sleeps if sleeps is not None else []
    return TrelloClient(KEY, TOKEN, transport=httpx.MockTransport(fake), sleep=sleeps.append)


# --- bentuk data -------------------------------------------------------------------


def test_board_export_has_same_shape_as_trello_json_export():
    fake = FakeTrello()
    board = make_client(fake).fetch_board_export(SHORT_LINK)

    assert board["id"] == BOARD_ID
    assert board["name"] == "Papan PuTI"
    for key in ("lists", "cards", "members", "labels", "actions"):
        assert isinstance(board[key], list) and board[key], key
    assert board["actions"][0]["memberCreator"]["username"] == "anggota"


def test_short_link_is_resolved_to_board_id_for_nested_requests():
    fake = FakeTrello()
    make_client(fake).fetch_board_export(SHORT_LINK)

    nested = [r.url.path for r in fake.requests[1:]]
    assert all(f"/boards/{BOARD_ID}/" in path for path in nested)


def test_actions_request_filters_relevant_types_and_member_fields():
    fake = FakeTrello()
    make_client(fake).fetch_actions(BOARD_ID)

    params = fake.action_calls()[0].url.params
    assert "updateCard" in params["filter"] and "createCard" in params["filter"]
    assert params["limit"] == str(PAGE_LIMIT)
    assert "username" in params["memberCreator_fields"]


# --- paginasi ----------------------------------------------------------------------


def test_actions_are_paginated_with_before_until_last_page():
    fake = FakeTrello(actions=make_actions(2500))
    actions = make_client(fake).fetch_actions(BOARD_ID)

    calls = fake.action_calls()
    assert len(calls) == 3
    assert "before" not in calls[0].url.params
    assert calls[1].url.params["before"] == actions[999]["id"]
    assert len(actions) == 2500
    assert len({a["id"] for a in actions}) == 2500, "tidak boleh ada action ganda"
    assert actions == sorted(actions, key=lambda a: a["id"], reverse=True)


def test_exactly_one_full_page_needs_one_extra_empty_request():
    fake = FakeTrello(actions=make_actions(PAGE_LIMIT))
    actions = make_client(fake).fetch_actions(BOARD_ID)

    assert len(actions) == PAGE_LIMIT
    assert len(fake.action_calls()) == 2


# --- kredensial ----------------------------------------------------------------------


def test_credentials_go_in_header_not_url():
    fake = FakeTrello()
    make_client(fake).fetch_board_export(BOARD_ID)

    for request in fake.requests:
        assert TOKEN not in str(request.url)
        assert KEY not in str(request.url)
        assert request.headers["authorization"] == (
            f'OAuth oauth_consumer_key="{KEY}", oauth_token="{TOKEN}"'
        )


def test_token_is_not_exposed_in_repr_or_settings():
    client = make_client(FakeTrello())
    settings = TrelloSettings(api_enabled=True, api_key=KEY, api_token=TOKEN)

    assert TOKEN not in repr(client)
    assert TOKEN not in repr(settings) and TOKEN not in str(settings.model_dump())


# --- error dan percobaan ulang ------------------------------------------------------


def test_rate_limit_is_retried_with_retry_after():
    sleeps: list[float] = []
    fake = FakeTrello(script=[429, 429])
    board = make_client(fake, sleeps).fetch_board_export(BOARD_ID)

    assert board["id"] == BOARD_ID
    assert sleeps == [3.0, 3.0]


def test_server_error_is_retried_with_backoff():
    sleeps: list[float] = []
    fake = FakeTrello(script=[502, 503])
    make_client(fake, sleeps).fetch_actions(BOARD_ID)

    assert sleeps == [2.0, 4.0]


def test_rate_limit_gives_up_after_max_retries():
    fake = FakeTrello(script=[429] * 10)
    with pytest.raises(TrelloRateLimitError):
        make_client(fake).fetch_actions(BOARD_ID)
    assert len(fake.requests) == 5  # 1 percobaan + 4 ulang


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_credentials_raise_auth_error_without_leaking_token(status):
    fake = FakeTrello(script=[status])
    with pytest.raises(TrelloAuthError) as exc_info:
        make_client(fake).fetch_board_export(BOARD_ID)
    assert TOKEN not in str(exc_info.value)
    assert len(fake.requests) == 1, "401/403 tidak boleh dicoba ulang"


def test_unknown_board_raises_not_found():
    fake = FakeTrello()
    with pytest.raises(TrelloNotFoundError):
        make_client(fake).fetch_board_export("ZzZz9999")


@pytest.mark.parametrize(
    "board_id", ["", "abc", "../members/me", "AbCd1234?x=1", "5f1a2b3c4d5e6f7a8b9c0d1e/actions"]
)
def test_invalid_board_id_is_rejected_before_any_request(board_id):
    fake = FakeTrello()
    with pytest.raises(TrelloNotFoundError):
        make_client(fake).fetch_board_export(board_id)
    assert fake.requests == []


# --- feature flag -------------------------------------------------------------------


def test_connector_is_disabled_by_default(monkeypatch):
    for name in ("TRELLO_API_ENABLED", "TRELLO_API_KEY", "TRELLO_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    settings = TrelloSettings(_env_file=None)

    assert settings.api_enabled is False
    with pytest.raises(TrelloDisabledError, match="nonaktif"):
        client_from_settings(settings)


def test_enabled_without_credentials_is_refused():
    with pytest.raises(TrelloDisabledError, match="wajib diisi"):
        client_from_settings(TrelloSettings(_env_file=None, api_enabled=True, api_key=KEY))


def test_enabled_with_credentials_builds_client():
    settings = TrelloSettings(_env_file=None, api_enabled=True, api_key=KEY, api_token=TOKEN)
    fake = FakeTrello()
    with client_from_settings(settings, transport=httpx.MockTransport(fake)) as client:
        assert client.fetch_board_export(BOARD_ID)["name"] == "Papan PuTI"


def test_settings_read_flag_from_environment(monkeypatch):
    monkeypatch.setenv("TRELLO_API_ENABLED", "true")
    monkeypatch.setenv("TRELLO_API_KEY", KEY)
    monkeypatch.setenv("TRELLO_API_TOKEN", TOKEN)
    settings = TrelloSettings(_env_file=None)

    assert settings.api_enabled is True
    assert settings.api_token.get_secret_value() == TOKEN


# --- CLI ------------------------------------------------------------------------------


def test_cli_writes_export_file(tmp_path, monkeypatch, capsys):
    fake = FakeTrello(actions=make_actions(1500))
    monkeypatch.setattr(fetch_board, "client_from_settings", lambda: make_client(fake))
    out = tmp_path / "board.json"

    assert fetch_board.main(["--board", SHORT_LINK, "--out", str(out)]) == 0

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["actions"]) == 1500
    assert "Action : 1500" in capsys.readouterr().out


def test_cli_reports_disabled_connector(tmp_path, monkeypatch, capsys):
    def disabled():
        raise TrelloDisabledError("Konektor Trello API nonaktif (TRELLO_API_ENABLED=false)")

    monkeypatch.setattr(fetch_board, "client_from_settings", disabled)
    out = tmp_path / "board.json"

    assert fetch_board.main(["--board", SHORT_LINK, "--out", str(out)]) == 1
    assert "nonaktif" in capsys.readouterr().err
    assert not out.exists()


def test_all_connector_errors_share_base_class():
    for error in (TrelloAuthError, TrelloDisabledError, TrelloNotFoundError, TrelloRateLimitError):
        assert issubclass(error, TrelloError)
