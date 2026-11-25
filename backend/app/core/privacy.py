"""Penyamaran data pribadi pada response API (DIG-95, story DIG-19).

Alamat surel author commit TeamGit tidak pernah ditampilkan apa adanya. Yang dikirim ke klien
adalah bentuk tersamar (`b***@puti.ac.id`), sedangkan nilai aslinya tetap tersimpan di basis
data untuk pencocokan identitas. Untuk identitas yang belum dipetakan, klien mendapat
`alias_ref`: penanda tak terbaca yang dicocokkan ulang di server saat alias dibuat.
"""

import hashlib
import hmac
import re
from typing import Any

from app.core.config import get_settings

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MASK = "***"


def mask_email(value: str) -> str:
    """`budi.santoso@puti.ac.id` menjadi `b***@puti.ac.id`. Teks tanpa `@` disamarkan penuh."""
    local, at, domain = value.strip().rpartition("@")
    if not at or not local or not domain:
        return MASK
    return f"{local[0]}{MASK}@{domain}"


def mask_emails_in_text(text: str) -> str:
    """Samarkan setiap alamat surel yang muncul di dalam teks bebas."""
    return EMAIL_PATTERN.sub(lambda match: mask_email(match.group(0)), text)


def mask_emails_deep(value: Any) -> Any:
    """Samarkan alamat surel di semua string dalam dict/list bertingkat (mis. JSON audit)."""
    if isinstance(value, str):
        return mask_emails_in_text(value)
    if isinstance(value, dict):
        return {key: mask_emails_deep(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_emails_deep(item) for item in value]
    return value


def alias_ref(source: str, key: str) -> str:
    """Penanda identitas yang stabil tetapi tidak bisa dibalik menjadi alamat surel."""
    secret = get_settings().jwt_secret_key.get_secret_value().encode()
    digest = hmac.new(secret, f"{source}:{key}".encode(), hashlib.sha256).hexdigest()
    return f"ref-{digest[:32]}"
