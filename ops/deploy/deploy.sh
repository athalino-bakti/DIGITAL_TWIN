#!/bin/sh
# Deploy staging J&C (DIG-205). Dijalankan di server staging, dari salinan repository:
#   sh ops/deploy/deploy.sh <commit>
# Biasanya dipanggil workflow "Deploy staging" lewat SSH setelah CI di main lulus.
#
# Langkah: ambil commit, backup basis data (bila sudah ada), build dan jalankan ulang container,
# lalu tunggu API siap. Gagal di langkah mana pun = kode keluar bukan 0, dan container lama
# tetap berjalan sampai `up` berhasil membuat yang baru.
set -eu

# Seluruh isi dibungkus fungsi supaya sh membacanya utuh sebelum `git checkout` mengganti
# berkas skrip ini dengan versi commit baru.
main() {
  commit=${1:?pakai: deploy.sh <commit>}
  ENV_FILE=${ENV_FILE:-staging.env}
  COMPOSE="docker compose -f compose.prod.yaml --env-file $ENV_FILE"

  cd "$(dirname "$0")/../.."
  [ -r "$ENV_FILE" ] || { echo "berkas $ENV_FILE tidak ada; lihat docs/STAGING.md" >&2; exit 2; }

  echo "== ambil $commit"
  git fetch --quiet origin
  git checkout --quiet --detach "$commit"

  if $COMPOSE --profile ops config --services | grep -qx backup \
    && $COMPOSE ps --status running --services | grep -qx db; then
    echo "== backup sebelum deploy"
    $COMPOSE run --rm backup
  fi

  echo "== build dan jalankan"
  $COMPOSE up -d --build --remove-orphans

  port=$(grep -E '^WEB_PORT=' "$ENV_FILE" | cut -d= -f2)
  port=${port:-8080}
  echo "== tunggu API siap di port $port"
  i=0
  until curl -fsS -o /dev/null "http://127.0.0.1:$port/api/v1/health/ready"; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
      echo "GAGAL: API belum siap setelah 2 menit" >&2
      $COMPOSE ps -a
      $COMPOSE logs --no-color --tail 80 migrate api web
      exit 1
    fi
    sleep 2
  done

  echo "$commit $(date -Iseconds)" > .deployed
  echo "deploy selesai: $commit"
}

main "$@"
