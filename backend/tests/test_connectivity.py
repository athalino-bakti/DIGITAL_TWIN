"""DIG-126: uji konektivitas ke Trello dan TeamGit, tanpa jaringan sungguhan."""

import socket

import httpx
import pytest
from pydantic import SecretStr

from app.integrations import connectivity
from app.integrations.connectivity import FAILED, OK, SKIPPED, run_checks
from app.integrations.teamgit.config import TeamGitSettings
from app.integrations.trello.config import TrelloSettings

KEY = "k" * 32
TOKEN = "token-rahasia-uji"


def trello(enabled=True, key=KEY, token=TOKEN, base="https://api.trello.com/1"):
    return TrelloSettings(
        _env_file=None,
        api_enabled=enabled,
        api_key=SecretStr(key) if key else None,
        api_token=SecretStr(token) if token else None,
        api_base_url=base,
    )


def teamgit(base="https://teamgit.example.ac.id"):
    return TeamGitSettings(_env_file=None, base_url=base, token=SecretStr("tg-rahasia"))


def resolver_ok(host, port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", port))]


def resolver_fail(host, port):
    raise socket.gaierror(-2, "Name or service not known")


class FakeSocket:
    def close(self):
        pass


def connector_ok(address, timeout):
    return FakeSocket()


def connector_fail(address, timeout):
    raise ConnectionRefusedError(111, "Connection refused")


def server(me_status=200):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/members/me"):
            return httpx.Response(me_status, json={"username": "kaur.puti"})
        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler), seen


def steps(results, target):
    return [(r.step, r.status) for r in results if r.target == target]


def run(trello_settings, teamgit_settings, transport, resolver=resolver_ok, connector=connector_ok):
    return run_checks(
        trello_settings,
        teamgit_settings,
        5.0,
        transport=transport,
        resolver=resolver,
        connector=connector,
    )


def test_all_steps_pass_when_network_and_token_are_fine():
    transport, seen = server()
    results = run(trello(), teamgit(), transport)

    assert steps(results, "trello") == [
        ("dns", OK),
        ("tcp", OK),
        ("https", OK),
        ("akses", OK),
    ]
    assert "kaur.puti" in [r for r in results if r.step == "akses"][0].detail
    # Token TeamGit belum bisa dicek sebelum konektornya ada.
    assert steps(results, "teamgit") == [
        ("dns", OK),
        ("tcp", OK),
        ("https", OK),
        ("akses", SKIPPED),
    ]
    me = [r for r in seen if r.url.path.endswith("/members/me")][0]
    assert TOKEN not in str(me.url), "token tidak boleh di query string"


def test_dns_failure_stops_the_target():
    transport, _ = server()
    results = run(trello(), teamgit(None), transport, resolver=resolver_fail)
    assert steps(results, "trello") == [("dns", FAILED)]


def test_closed_port_stops_before_https():
    transport, seen = server()
    results = run(trello(), teamgit(None), transport, connector=connector_fail)
    assert steps(results, "trello") == [("dns", OK), ("tcp", FAILED)]
    assert seen == []


def test_tls_or_timeout_failure_is_reported():
    def broken(request):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    results = run(trello(), teamgit(None), httpx.MockTransport(broken))
    https = [r for r in results if r.step == "https"][0]
    assert https.status == FAILED and "sertifikat TLS" in https.detail


def test_rejected_token_fails_the_access_step():
    transport, _ = server(me_status=401)
    results = run(trello(), teamgit(None), transport)
    access = [r for r in results if r.target == "trello" and r.step == "akses"][0]
    assert access.status == FAILED and "ditolak" in access.detail


def test_access_is_skipped_when_connector_disabled_but_missing_token_fails():
    transport, _ = server()
    disabled = run(trello(enabled=False), teamgit(None), transport)
    assert steps(disabled, "trello")[-1] == ("akses", SKIPPED)

    no_token = run(trello(token=None), teamgit(None), transport)
    assert steps(no_token, "trello")[-1] == ("akses", FAILED)


def test_unconfigured_teamgit_is_skipped_not_failed():
    transport, _ = server()
    assert steps(run(trello(), teamgit(None), transport), "teamgit") == [("url", SKIPPED)]


def test_non_https_url_is_rejected():
    transport, _ = server()
    results = run(trello(), teamgit("http://teamgit.example.ac.id"), transport)
    assert steps(results, "teamgit") == [("url", FAILED)]


def test_proxy_skips_direct_dns_and_tcp(monkeypatch):
    monkeypatch.setattr(connectivity, "_uses_proxy", lambda host: "proxy.kampus.ac.id")
    calls = []

    def resolver(host, port):
        calls.append(host)
        return resolver_ok(host, port)

    # transport None memicu deteksi proxy; request HTTPS-nya dipalsukan lewat httpx.Client.
    real_client = httpx.Client
    fake_transport = server()[0]
    monkeypatch.setattr(
        connectivity.httpx,
        "Client",
        lambda **kw: real_client(**{**kw, "transport": fake_transport}),
    )
    results = connectivity.check_reachable(
        "trello", "https://api.trello.com/1", 5.0, resolver=resolver, connector=connector_fail
    )
    assert [(r.step, r.status) for r in results] == [
        ("dns", SKIPPED),
        ("tcp", SKIPPED),
        ("https", OK),
    ]
    assert calls == []


def test_cli_output_and_exit_code_never_show_secrets(monkeypatch, capsys):
    transport, _ = server(me_status=401)

    def fake_run(trello_settings, teamgit_settings, timeout):
        return run(trello(), teamgit(), transport)

    monkeypatch.setattr(connectivity, "run_checks", fake_run)
    assert connectivity.main([]) == 1
    out = capsys.readouterr().out
    assert "gagal" in out and TOKEN not in out and KEY not in out and "tg-rahasia" not in out

    transport_ok, _ = server()
    monkeypatch.setattr(
        connectivity, "run_checks", lambda *a: run(trello(), teamgit(), transport_ok)
    )
    assert connectivity.main([]) == 0
    assert "Semua yang diperiksa lolos" in capsys.readouterr().out


@pytest.mark.parametrize("status", [500, 503])
def test_trello_server_error_is_a_failed_access_without_retry_wait(status):
    transport, seen = server(me_status=status)
    results = run(trello(), teamgit(None), transport)
    assert steps(results, "trello")[-1] == ("akses", FAILED)
    assert len([r for r in seen if r.url.path.endswith("/members/me")]) == 1
