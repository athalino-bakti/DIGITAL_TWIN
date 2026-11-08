"""Buat akun pengguna dari terminal (belum ada halaman kelola user sampai RBAC DIG-18).

Dari folder backend:
    python -m app.modules.auth.create_user --username bagas --full-name "Bagas Haris Saputro"
    python -m app.modules.auth.create_user --username davi --full-name "Davi" --resource-id RES-001

Password diminta lewat prompt (tidak tampil dan tidak tersimpan di riwayat terminal).
"""

import argparse
import getpass
import re
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.modules.auth.models import USERNAME_PATTERN, AppUser
from app.modules.auth.security import hash_password

MIN_PASSWORD_LENGTH = 8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Buat akun pengguna Digital Twin PuTI")
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--resource-id", default=None, help="Opsional, contoh RES-001")
    args = parser.parse_args(argv)

    username = args.username.strip().lower()
    if not re.match(USERNAME_PATTERN, username):
        print("Username 3-50 karakter: huruf kecil, angka, titik, _ atau -", file=sys.stderr)
        return 1

    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password minimal {MIN_PASSWORD_LENGTH} karakter", file=sys.stderr)
        return 1
    if getpass.getpass("Ulangi password: ") != password:
        print("Password tidak sama", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        if db.scalar(select(AppUser.user_id).where(AppUser.username == username)):
            print(f"Username {username} sudah dipakai", file=sys.stderr)
            return 1
        db.add(
            AppUser(
                username=username,
                full_name=args.full_name.strip(),
                password_hash=hash_password(password),
                resource_id=args.resource_id,
            )
        )
        try:
            db.commit()
        except IntegrityError as exc:
            print(f"Gagal menyimpan: {exc.orig}", file=sys.stderr)
            return 1
    print(f"Akun {username} dibuat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
