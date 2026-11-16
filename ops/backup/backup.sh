#!/bin/sh
# Backup basis data J&C (DIG-218). Dijalankan di container `backup` (compose.prod.yaml):
#   docker compose -f compose.prod.yaml run --rm backup
#
# Hasil di $BACKUP_DIR (bawaan /backups, di host ./backups):
#   daily/jc_YYYYMMDD_HHMMSS.dump        pg_dump format custom, semua data dan skema
#   daily/jc_YYYYMMDD_HHMMSS.roles.sql   role cluster (jc_app, ...), untuk server baru
#   weekly/...                           salinan backup hari Minggu
# Simpan BACKUP_KEEP_DAILY backup harian dan BACKUP_KEEP_WEEKLY backup mingguan terbaru.
# Koneksi dari variabel standar PostgreSQL: PGHOST, PGUSER, PGPASSWORD, PGDATABASE.
set -eu

BACKUP_DIR=${BACKUP_DIR:-/backups}
KEEP_DAILY=${BACKUP_KEEP_DAILY:-7}
KEEP_WEEKLY=${BACKUP_KEEP_WEEKLY:-4}
stamp=$(date +%Y%m%d_%H%M%S)
name="jc_${stamp}"

umask 077  # berkas backup berisi seluruh data dan hash password
mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"
tmp="$BACKUP_DIR/daily/.${name}.tmp"
trap 'rm -f "$tmp" "$tmp.roles"' EXIT

echo "backup $PGDATABASE di $PGHOST -> $BACKUP_DIR/daily/$name.dump"
pg_dump --format=custom --compress=6 --file="$tmp" "$PGDATABASE"
# Daftar isi harus bisa dibaca; berkas terpotong atau rusak gagal di sini.
tables=$(pg_restore --list "$tmp" | grep -c ' TABLE DATA ' || true)
if [ "$tables" -eq 0 ]; then
  echo "GAGAL: backup tidak berisi data tabel" >&2
  exit 1
fi
# Tanpa hash password: password role diatur ulang saat server baru disiapkan.
pg_dumpall --roles-only --no-role-passwords > "$tmp.roles"
mv "$tmp" "$BACKUP_DIR/daily/$name.dump"
mv "$tmp.roles" "$BACKUP_DIR/daily/$name.roles.sql"

if [ "$(date +%u)" = 7 ]; then
  cp "$BACKUP_DIR/daily/$name.dump" "$BACKUP_DIR/daily/$name.roles.sql" "$BACKUP_DIR/weekly/"
fi

prune() {  # prune <folder> <jumlah disimpan>
  ls -1 "$1"/jc_*.dump 2>/dev/null | sort -r | tail -n +"$(($2 + 1))" | while read -r old; do
    rm -f "$old" "${old%.dump}.roles.sql"
    echo "hapus backup lama $(basename "$old")"
  done
}
prune "$BACKUP_DIR/daily" "$KEEP_DAILY"
prune "$BACKUP_DIR/weekly" "$KEEP_WEEKLY"

size=$(du -h "$BACKUP_DIR/daily/$name.dump" | cut -f1)
echo "selesai: $name.dump ($size, $tables tabel berisi data)"
