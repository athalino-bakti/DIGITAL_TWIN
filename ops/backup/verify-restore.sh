#!/bin/sh
# Uji restore (DIG-218): pulihkan backup terbaru ke basis data sementara, bandingkan dengan
# basis data asal, lalu hapus basis data sementara. Jalankan rutin, misalnya seminggu sekali:
#   docker compose -f compose.prod.yaml run --rm --entrypoint sh backup /ops/verify-restore.sh
#
# Gagal (kode 1) bila restore error, versi migrasi berbeda, ada tabel yang hilang, atau tabel
# yang berisi data di asal kosong setelah dipulihkan. Selisih jumlah baris lain hanya
# diperingatkan, karena data bisa berubah sejak backup dibuat; dengan --strict semua selisih
# dianggap gagal (dipakai di CI, saat tidak ada yang menulis).
set -eu

BACKUP_DIR=${BACKUP_DIR:-/backups}
strict=0
[ "${1:-}" = "--strict" ] && strict=1

dump=$(ls -1 "$BACKUP_DIR"/daily/jc_*.dump 2>/dev/null | sort -r | head -n 1)
[ -n "$dump" ] || { echo "GAGAL: belum ada backup di $BACKUP_DIR/daily" >&2; exit 1; }
check="jc_cek_restore_$(date +%Y%m%d%H%M%S)"
trap 'dropdb --if-exists "$check" >/dev/null 2>&1 || true' EXIT

echo "uji restore $(basename "$dump") ke $check"
sh "$(dirname "$0")/restore.sh" "$dump" "$check" >/dev/null

counts() {  # counts <basis data>: "schema.tabel jumlah" untuk semua tabel aplikasi
  # Semua schema milik aplikasi, termasuk `twinner` (#14), bukan hanya public.
  psql -d "$1" -At -F ' ' -c "SELECT table_schema, table_name FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND table_schema NOT LIKE 'pg\_%' AND table_type = 'BASE TABLE'
    ORDER BY table_schema, table_name" |
  while read -r schema table; do
    echo "$schema.$table $(psql -d "$1" -Atc "SELECT count(*) FROM \"$schema\".\"$table\"")"
  done
}

counts "$PGDATABASE" > /tmp/asal.txt
counts "$check" > /tmp/pulih.txt
failed=0
warned=0

src_version=$(psql -d "$PGDATABASE" -Atc "SELECT version_num FROM alembic_version")
new_version=$(psql -d "$check" -Atc "SELECT version_num FROM alembic_version")
if [ "$src_version" != "$new_version" ]; then
  echo "GAGAL: versi migrasi asal $src_version, hasil restore $new_version"
  failed=1
fi

while read -r table src; do
  new=$(grep "^$table " /tmp/pulih.txt | cut -d' ' -f2)
  if [ -z "$new" ]; then
    echo "GAGAL: tabel $table tidak ada di hasil restore"; failed=1
  elif [ "$src" != "$new" ]; then
    if [ "$new" = 0 ] || [ "$strict" = 1 ]; then
      echo "GAGAL: $table asal $src baris, hasil restore $new"; failed=1
    else
      echo "PERINGATAN: $table asal $src baris, hasil restore $new (data berubah sejak backup?)"
      warned=1
    fi
  fi
done < /tmp/asal.txt

tables=$(wc -l < /tmp/asal.txt | tr -d ' ')
rows=$(awk '{s += $2} END {print s + 0}' /tmp/pulih.txt)
if [ "$failed" = 1 ]; then
  echo "UJI RESTORE GAGAL"
  exit 1
fi
[ "$warned" = 1 ] && echo "uji restore lolos dengan peringatan"
echo "uji restore lolos: $tables tabel, $rows baris, versi migrasi $new_version"
