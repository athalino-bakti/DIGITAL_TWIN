"""Unduh satu papan Trello lewat API ke berkas berformat ekspor JSON.

Dari folder backend, dengan TRELLO_API_ENABLED, TRELLO_API_KEY, dan TRELLO_API_TOKEN di .env:
    python -m app.integrations.trello.fetch_board --board abc12345 --out board.json

--board menerima shortLink dari URL papan (trello.com/b/<shortLink>/...) atau ID 24 karakter.
Berkas hasilnya bisa diproses parser ekspor JSON Trello (DIG-118) seperti ekspor manual.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from app.integrations.trello.client import TrelloError, client_from_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unduh papan Trello ke JSON format ekspor")
    parser.add_argument("--board", required=True, help="shortLink atau ID papan")
    parser.add_argument("--out", required=True, type=Path, help="Berkas JSON tujuan")
    args = parser.parse_args(argv)

    try:
        with client_from_settings() as client:
            board = client.fetch_board_export(args.board)
    except TrelloError as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 1

    args.out.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
    action_types = Counter(action["type"] for action in board["actions"])
    print(f"Papan  : {board['name']}")
    print(f"List   : {len(board['lists'])}")
    print(f"Kartu  : {len(board['cards'])}")
    print(f"Anggota: {len(board['members'])}")
    print(f"Action : {len(board['actions'])} ({dict(action_types.most_common())})")
    print(f"Disimpan ke {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
