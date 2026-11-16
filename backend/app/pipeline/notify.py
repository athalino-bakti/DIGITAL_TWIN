"""Notifikasi kegagalan job impor lewat webhook (DIG-129).

Payload berisi `text` (Slack, Google Chat, Mattermost) dan `content` (Discord), jadi satu
URL webhook dari salah satu layanan itu cukup. Gagal mengirim notifikasi hanya dicatat di
log sebagai warning: kegagalan notifikasi tidak boleh menutupi kegagalan job yang asli.
"""

import logging

import httpx

from app.pipeline.config import PipelineSettings

logger = logging.getLogger("app.pipeline.notify")
MAX_MESSAGE = 1800  # di bawah batas 2000 karakter Discord


def send_notification(
    settings: PipelineSettings, message: str, transport: httpx.BaseTransport | None = None
) -> bool:
    """Kirim pesan ke webhook. True bila terkirim, False bila tidak diatur atau gagal."""
    if settings.notify_webhook_url is None:
        logger.info("notifikasi tidak dikirim: NOTIFY_WEBHOOK_URL kosong")
        return False
    text = message if len(message) <= MAX_MESSAGE else message[: MAX_MESSAGE - 1] + "…"
    try:
        with httpx.Client(timeout=settings.notify_timeout_seconds, transport=transport) as http:
            response = http.post(
                settings.notify_webhook_url.get_secret_value(),
                json={"text": text, "content": text},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        # URL webhook rahasia, jadi yang dicatat hanya jenis error dan status.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning(
            "notifikasi gagal dikirim",
            extra={"error_type": type(exc).__name__, "http_status": status},
        )
        return False
    return True
