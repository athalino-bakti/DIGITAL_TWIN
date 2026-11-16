"""Header keamanan untuk setiap respons API (DIG-208).

Di staging, nginx (frontend/nginx/default.conf.template) sudah memasang CSP dan header lain
untuk semua respons. Middleware ini memastikan respons API tetap aman bila API dibuka
langsung tanpa nginx (development, uji, atau salah konfigurasi):

- `Cache-Control: no-store`: data kerja dan token tidak disimpan di cache browser atau proxy,
  kecuali endpoint sudah menentukan cache-nya sendiri;
- `X-Content-Type-Options: nosniff`: JSON tidak ditafsirkan sebagai HTML;
- `X-Frame-Options: DENY` dan CSP `frame-ancestors 'none'`: respons API tidak bisa dibingkai;
- `Referrer-Policy: no-referrer`.

Halaman dokumentasi FastAPI (`/docs`, `/redoc`) dilewati karena memuat skrip dari CDN; di
staging halaman itu tidak terjangkau dari luar karena nginx hanya meneruskan `/api/`.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_HEADERS = {
    b"cache-control": b"no-store",
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"content-security-policy": b"default-src 'none'; frame-ancestors 'none'",
}
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    """Middleware ASGI murni, supaya respons streaming dan error ikut mendapat header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(DOCS_PATHS):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers.extend(
                    (name, value) for name, value in API_HEADERS.items() if name not in present
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
