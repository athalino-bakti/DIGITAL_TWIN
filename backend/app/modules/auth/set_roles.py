"""Atur peran aplikasi seorang pengguna dari terminal (sampai halaman kelola akun tersedia).

Dari folder backend:
    python -m app.modules.auth.set_roles --list
    python -m app.modules.auth.set_roles --username bagas --role admin_data --role system_analyst
    python -m app.modules.auth.set_roles --username bagas --clear

Peran lama pengguna diganti seluruhnya dengan daftar --role. Perubahan langsung berlaku
tanpa login ulang.
"""

import argparse
import sys

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.auth.models import AppUser
from app.modules.auth.rbac_models import AppRole, UserAppRole


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atur peran aplikasi pengguna")
    parser.add_argument("--username")
    parser.add_argument("--role", action="append", default=[], help="Bisa diulang")
    parser.add_argument("--clear", action="store_true", help="Hapus semua peran pengguna")
    parser.add_argument("--list", action="store_true", help="Tampilkan peran yang tersedia")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        roles = {role.role_code: role.role_name for role in db.scalars(select(AppRole))}
        if args.list:
            for code, name in sorted(roles.items()):
                print(f"{code:<16} {name}")
            return 0

        if not args.username or (not args.role and not args.clear):
            print("Isi --username dan --role (atau --clear)", file=sys.stderr)
            return 1
        if args.clear and args.role:
            print("Pilih salah satu: --role atau --clear", file=sys.stderr)
            return 1
        unknown = sorted(set(args.role) - set(roles))
        if unknown:
            print(f"Peran tidak dikenal: {', '.join(unknown)}. Lihat --list", file=sys.stderr)
            return 1

        username = args.username.strip().lower()
        user = db.scalar(select(AppUser).where(AppUser.username == username))
        if user is None:
            print(f"Username {username} tidak ditemukan", file=sys.stderr)
            return 1

        db.execute(delete(UserAppRole).where(UserAppRole.user_id == user.user_id))
        for code in sorted(set(args.role)):
            db.add(UserAppRole(user_id=user.user_id, role_code=code))
        db.commit()

    assigned = ", ".join(sorted(set(args.role))) or "(tanpa peran)"
    print(f"Peran {username}: {assigned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
