"""Aturan tanggal `change_event_details` (DIG-221, DATA_CONTRACT 7.3).

`approved_date` dan `resolved_date` tidak boleh lebih awal dari `event_date` kejadian di D-10.
Aturan ini ada di validator, bukan constraint basis data, karena kedua sisi berada di tabel
berbeda. Karena itu ia harus dicek dari dua arah:

- saat detail disimpan (endpoint atau importer `change_event_details`): `validate_detail`;
- saat `event_date` kejadian diubah (PATCH D-10 di `change_event_service.update_change_event`,
  PR #24): `check_event_date_change`, supaya detail yang sudah ada tidak menjadi lebih awal
  dari tanggal kejadian yang baru.

Menghapus kejadian tidak perlu dicek: detailnya ikut terhapus (ON DELETE CASCADE).
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.models import ChangeEvent
from app.modules.data.service import DataValidationError, FieldError
from app.modules.data.support_models import ChangeEventDetail

DETAIL_DATES = (
    ("approved_date", "Tanggal persetujuan"),
    ("resolved_date", "Tanggal selesai"),
)


def check_detail_dates(
    event_date: date, approved_date: date | None, resolved_date: date | None
) -> list[FieldError]:
    """Error per kolom bila tanggal detail lebih awal dari tanggal kejadian. Kosong selalu lolos."""
    values = {"approved_date": approved_date, "resolved_date": resolved_date}
    return [
        FieldError(
            field,
            f"{label} tidak boleh sebelum tanggal kejadian ({event_date.isoformat()})",
            "before_event_date",
        )
        for field, label in DETAIL_DATES
        if values[field] is not None and values[field] < event_date
    ]


def validate_detail(db: Session, values: Mapping[str, Any]) -> None:
    """Cek satu detail terhadap `event_date` kejadiannya; DataValidationError (422) bila salah."""
    event_date = db.scalar(
        select(ChangeEvent.event_date).where(ChangeEvent.event_id == values["event_id"])
    )
    if event_date is None:
        raise DataValidationError(
            [
                FieldError(
                    "event_id", f"Kejadian {values['event_id']} tidak terdaftar", "event_not_found"
                )
            ]
        )
    errors = check_detail_dates(
        event_date, values.get("approved_date"), values.get("resolved_date")
    )
    if errors:
        raise DataValidationError(errors)


def check_event_date_change(db: Session, event_id: str, new_event_date: date) -> list[FieldError]:
    """Error di kolom `event_date` bila tanggal baru melewati tanggal di detail kejadian itu."""
    detail = db.get(ChangeEventDetail, event_id)
    if detail is None:
        return []
    filled = [d for d in (detail.approved_date, detail.resolved_date) if d is not None]
    if not filled or new_event_date <= min(filled):
        return []
    return [
        FieldError(
            "event_date",
            "Tidak boleh setelah tanggal persetujuan atau tanggal selesai di detail kejadian "
            f"({min(filled).isoformat()})",
            "after_detail_dates",
        )
    ]
