"""Peran aplikasi dan izin (RBAC, DIG-18).

Terpisah dari D-03 `roles` (peran kerja di PuTI seperti Back-End Developer). Tabel di sini
mengatur hak akses aplikasi J&C: satu pengguna boleh punya banyak peran aplikasi, dan hak
aksesnya adalah gabungan izin dari semua perannya (core RBAC, Sandhu et al., 1996).
"""

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Kode peran: huruf kecil dan garis bawah, contoh `kaur_asman`.
ROLE_CODE_PATTERN = "^[a-z][a-z_]{2,29}$"
# Kode izin: `<objek>:<aksi>`, contoh `master_data:write`.
PERMISSION_CODE_PATTERN = "^[a-z][a-z_]*:[a-z][a-z_]*$"


class AppRole(Base):
    __tablename__ = "app_role"
    __table_args__ = (
        CheckConstraint(f"role_code ~ '{ROLE_CODE_PATTERN}'", name="role_code_format"),
    )

    role_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    role_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))


class Permission(Base):
    __tablename__ = "permission"
    __table_args__ = (
        CheckConstraint(
            f"permission_code ~ '{PERMISSION_CODE_PATTERN}'", name="permission_code_format"
        ),
    )

    permission_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    description: Mapped[str] = mapped_column(String(500))


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_code: Mapped[str] = mapped_column(
        ForeignKey("app_role.role_code", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permission.permission_code", ondelete="CASCADE"), primary_key=True
    )


class UserAppRole(Base):
    __tablename__ = "user_app_role"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.user_id", ondelete="CASCADE"), primary_key=True
    )
    role_code: Mapped[str] = mapped_column(
        ForeignKey("app_role.role_code", ondelete="RESTRICT"), primary_key=True
    )
