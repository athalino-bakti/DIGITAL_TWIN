"""Akun pengguna aplikasi (tabel internal J&C, bukan bagian Data Dictionary D-01 s.d. D-11).

Satu akun boleh ditautkan ke satu anggota tim (resources). Akun admin data atau akun
uji yang bukan anggota tim cukup mengosongkan resource_id.
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Huruf kecil, angka, titik, garis bawah, dan tanda hubung; 3-50 karakter.
USERNAME_PATTERN = "^[a-z0-9._-]{3,50}$"


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (CheckConstraint(f"username ~ '{USERNAME_PATTERN}'", name="username_format"),)

    user_id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    resource_id: Mapped[str | None] = mapped_column(
        ForeignKey("resources.resource_id", ondelete="SET NULL"), unique=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
