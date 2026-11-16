#!/bin/sh
# Pulihkan backup ke basis data baru (DIG-218).
#   docker compose -f compose.prod.yaml run --rm --entrypoint sh backup /ops/restore.sh \
#     /backups/daily/jc_20261116_021700.dump digital_twin_pulih
#
# Basis data tujuan dibuat baru dan tidak boleh sudah ada, supaya data yang sedang dipakai tidak
# tertimpa tanpa sengaja. Setelah diperiksa, arahkan aplikasi ke basis data itu (DATABASE_URL /
# POSTGRES_DB) atau ganti nama: lihat docs/BACKUP.md.
set -eu

if [ $# -ne 2 ]; then
  echo "pakai: restore.sh <berkas .dump> <nama basis data baru>" >&2
  exit 2
fi
dump=$1
target=$2
case "$target" in
  *[!a-z0-9_]* | "") echo "nama basis data hanya huruf kecil, angka, dan _" >&2; exit 2 ;;
esac
[ -r "$dump" ] || { echo "berkas $dump tidak ada" >&2; exit 2; }

exists=$(psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$target'")
if [ "$exists" = 1 ]; then
  echo "basis data $target sudah ada; pilih nama lain atau hapus dulu dengan sadar" >&2
  exit 1
fi

roles="${dump%.dump}.roles.sql"
if [ -r "$roles" ]; then
  # Role sudah ada di server yang sama; di server baru role dibuat dari berkas ini.
  psql -d postgres -q -v ON_ERROR_STOP=0 -f "$roles" >/dev/null 2>&1 || true
fi

createdb "$target"
pg_restore --exit-on-error --no-owner --role="$PGUSER" --dbname="$target" "$dump"
echo "dipulihkan ke $target"
psql -d "$target" -Atc "SELECT 'versi migrasi: ' || version_num FROM alembic_version"
