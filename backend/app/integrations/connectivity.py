"""Uji konektivitas server aplikasi ke Trello API dan TeamGit (DIG-126).

Jalankan dari folder backend, di server yang akan menjalankan impor:
    python -m app.integrations.connectivity
    python -m app.integrations.connectivity --timeout 5

Untuk setiap tujuan diperiksa berurutan, berhenti di langkah pertama yang gagal:
1. DNS   : nama host bisa di-resolve;
2. TCP   : port (443) bisa dibuka;
3. HTTPS : sertifikat TLS sah dan server menjawab (status HTTP apa pun dianggap terjangkau);
4. Akses : kredensial diterima (Trello, hanya bila TRELLO_API_ENABLED dan key/token terisi).

Bila host itu melewati proxy (HTTPS_PROXY/HTTP_PROXY), langkah DNS dan TCP langsung dilewati
karena koneksi keluar memang lewat proxy; langkah HTTPS tetap memakai proxy yang sama.

Hasil tidak pernah memuat key atau token. Kode keluar 0 bila semua yang diperiksa lolos,
1 bila ada yang gagal. Tujuan yang belum dikonfigurasi ditandai "dilewati", bukan gagal.
"""

import argparse
import socket
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.integrations.teamgit.config import TeamGitSettings, get_teamgit_settings
from app.integrations.trello.client import TrelloAuthError, TrelloClient, TrelloError
from app.integrations.trello.config import TrelloSettings, get_trello_settings

OK, FAILED, SKIPPED = "lolos", "gagal", "dilewati"

Resolver = Callable[[str, int], list]
Connector = Callable[[tuple[str, int], float], socket.socket]


@dataclass(frozen=True)
class Check:
    target: str
    step: str
    status: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.status:^8}] {self.target:<7} {self.step:<6} {self.detail}"


def _uses_proxy(host: str) -> str | None:
    proxies = urllib.request.getproxies()
    proxy = proxies.get("https") or proxies.get("all")
    if proxy and not urllib.request.proxy_bypass(host):
        return urlsplit(proxy).hostname or proxy
    return None


def _default_connector(address: tuple[str, int], timeout: float) -> socket.socket:
    return socket.create_connection(address, timeout=timeout)


def check_reachable(
    target: str,
    base_url: str,
    timeout: float,
    resolver: Resolver = socket.getaddrinfo,
    connector: Connector = _default_connector,
    transport: httpx.BaseTransport | None = None,
) -> list[Check]:
    """Langkah DNS, TCP, dan HTTPS ke satu alamat. Berhenti di langkah pertama yang gagal."""
    parts = urlsplit(base_url)
    host = parts.hostname
    if parts.scheme != "https" or not host:
        return [Check(target, "url", FAILED, f"alamat harus https:// (sekarang {base_url!r})")]
    port = parts.port or 443
    results: list[Check] = []

    proxy = _uses_proxy(host) if transport is None else None
    if proxy:
        note = f"lewat proxy {proxy}"
        results += [Check(target, "dns", SKIPPED, note), Check(target, "tcp", SKIPPED, note)]
    else:
        try:
            addresses = sorted({info[4][0] for info in resolver(host, port)})
        except (OSError, UnicodeError) as exc:
            return [Check(target, "dns", FAILED, f"{host} tidak bisa di-resolve ({exc})")]
        results.append(Check(target, "dns", OK, f"{host} -> {', '.join(addresses[:3])}"))
        started = time.monotonic()
        try:
            connector((host, port), timeout).close()
        except OSError as exc:
            results.append(Check(target, "tcp", FAILED, f"port {port} tertutup ({exc})"))
            return results
        elapsed = (time.monotonic() - started) * 1000
        results.append(Check(target, "tcp", OK, f"port {port} terbuka ({elapsed:.0f} ms)"))

    try:
        with httpx.Client(timeout=timeout, transport=transport) as http:
            response = http.get(base_url)
    except httpx.HTTPError as exc:
        kind = "sertifikat TLS" if "certificate" in str(exc).lower() else type(exc).__name__
        results.append(Check(target, "https", FAILED, f"tidak terjangkau: {kind}"))
        return results
    results.append(Check(target, "https", OK, f"server menjawab HTTP {response.status_code}"))
    return results


def check_trello(
    settings: TrelloSettings,
    timeout: float,
    transport: httpx.BaseTransport | None = None,
    **network,
) -> list[Check]:
    results = check_reachable(
        "trello", settings.api_base_url, timeout, transport=transport, **network
    )
    if any(r.status == FAILED for r in results):
        return results
    if not settings.api_enabled:
        return [*results, Check("trello", "akses", SKIPPED, "TRELLO_API_ENABLED=false")]
    if settings.api_key is None or settings.api_token is None:
        return [*results, Check("trello", "akses", FAILED, "TRELLO_API_KEY/TOKEN kosong")]
    client = TrelloClient(
        settings.api_key.get_secret_value(),
        settings.api_token.get_secret_value(),
        base_url=settings.api_base_url,
        timeout=timeout,
        max_retries=0,
        transport=transport,
    )
    try:
        username = client.fetch_me().get("username") or "?"
    except TrelloAuthError:
        return [*results, Check("trello", "akses", FAILED, "key/token ditolak Trello (401/403)")]
    except TrelloError as exc:
        return [*results, Check("trello", "akses", FAILED, str(exc))]
    finally:
        client.close()
    return [*results, Check("trello", "akses", OK, f"token milik akun {username}")]


def check_teamgit(
    settings: TeamGitSettings,
    timeout: float,
    transport: httpx.BaseTransport | None = None,
    **network,
) -> list[Check]:
    if not settings.base_url:
        return [Check("teamgit", "url", SKIPPED, "TEAMGIT_BASE_URL kosong")]
    results = check_reachable("teamgit", settings.base_url, timeout, transport=transport, **network)
    if any(r.status == FAILED for r in results):
        return results
    # Endpoint untuk memeriksa token bergantung pada jenis TeamGit; ditambahkan bersama
    # konektornya (DIG-122).
    return [*results, Check("teamgit", "akses", SKIPPED, "cek token menunggu konektor DIG-122")]


def run_checks(
    trello: TrelloSettings, teamgit: TeamGitSettings, timeout: float, **network
) -> list[Check]:
    return check_trello(trello, timeout, **network) + check_teamgit(teamgit, timeout, **network)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Uji konektivitas ke Trello API dan TeamGit")
    parser.add_argument("--timeout", type=float, default=10.0, help="detik per langkah")
    args = parser.parse_args(argv)

    results = run_checks(get_trello_settings(), get_teamgit_settings(), args.timeout)
    for result in results:
        print(result)
    failed = [r for r in results if r.status == FAILED]
    print(f"\n{len(failed)} langkah gagal." if failed else "\nSemua yang diperiksa lolos.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
