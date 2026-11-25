"""Matriks akses per peran untuk semua endpoint API (DIG-207, story DIG-50).

Matriks dibaca langsung dari aplikasi FastAPI: izin `require_permission` di setiap route
ditambah sedikit aturan khusus di bawah. Hasilnya dipakai dua kali:

- `tests/test_access_matrix.py` memanggil setiap endpoint sebagai setiap peran dan memastikan
  jawabannya sesuai matriks (401 tanpa login, 403 tanpa izin, lolos bila berizin);
- dokumen `docs/ACCESS_MATRIX.md` dibuat dari matriks yang sama.

Dari folder backend:
    python -m app.qa.access_matrix                          # cetak ke layar
    python -m app.qa.access_matrix --write ../docs/ACCESS_MATRIX.md
"""

import argparse
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.modules.auth.permissions import ROLES, Perm

API_PREFIX = "/api/v1"

# Endpoint tanpa login.
PUBLIC = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/ready"),
    ("POST", "/api/v1/auth/login"),
}
# Cukup login, tanpa izin tertentu.
LOGIN_ONLY = {("GET", "/api/v1/auth/me")}
# Izin diperiksa di dalam handler: cukup salah satu dari izin berikut.
ANY_OF: dict[tuple[str, str], frozenset[Perm]] = {
    # Heatmap: workload:read_all untuk semua anggota, workload:read_own hanya dirinya (DIG-19).
    ("GET", "/api/v1/digital-twin/workload-heatmap"): frozenset(
        {Perm.WORKLOAD_READ_ALL, Perm.WORKLOAD_READ_OWN}
    ),
}


@dataclass(frozen=True)
class Rule:
    method: str
    path: str
    kind: str  # public | login | all_of | any_of
    perms: frozenset[Perm]

    def allows(self, granted: set[str] | frozenset[str]) -> bool:
        if self.kind in ("public", "login"):
            return True
        if self.kind == "any_of":
            return bool(self.perms & granted)
        return self.perms <= granted

    @property
    def needs_login(self) -> bool:
        return self.kind != "public"


def required_permissions(dependant) -> set[Perm]:
    found: set[Perm] = set(getattr(dependant.call, "required_permissions", ()))
    for sub in dependant.dependencies:
        found |= required_permissions(sub)
    return found


def walk(routes, prefix: str = "", inherited: frozenset = frozenset()) -> Iterator:
    """Semua APIRoute beserta path lengkapnya, termasuk router yang di-include bertingkat."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route, inherited
        elif hasattr(route, "original_router"):
            context = route.include_context
            extra = frozenset(
                perm
                for dependency in context.dependencies
                for perm in getattr(dependency.dependency, "required_permissions", ())
            )
            yield from walk(
                route.original_router.routes, prefix + context.prefix, inherited | extra
            )


def access_rules(app: FastAPI) -> list[Rule]:
    """Aturan akses setiap (method, path) di aplikasi, urut path lalu method."""
    rules = []
    for path, route, inherited in walk(app.routes):
        if not path.startswith(API_PREFIX):
            continue
        perms = frozenset(inherited | required_permissions(route.dependant))
        for method in route.methods:
            key = (method, path)
            if key in PUBLIC:
                rules.append(Rule(method, path, "public", frozenset()))
            elif key in LOGIN_ONLY:
                rules.append(Rule(method, path, "login", frozenset()))
            elif key in ANY_OF:
                rules.append(Rule(method, path, "any_of", ANY_OF[key]))
            else:
                rules.append(Rule(method, path, "all_of", perms))
    order = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}
    return sorted(rules, key=lambda r: (r.path, order.get(r.method, 9)))


def role_permissions() -> dict[str, frozenset[str]]:
    return {code: frozenset(p.value for p in perms) for code, (_, _, perms) in ROLES.items()}


def markdown(app: FastAPI) -> str:
    roles = role_permissions()
    labels = [ROLES[code][0] for code in roles]
    lines = [
        "# Matriks akses per peran (DIG-207)",
        "",
        "Dibuat otomatis dari kode dengan `python -m app.qa.access_matrix --write "
        "../docs/ACCESS_MATRIX.md` (dari folder backend). Setiap baris diuji lewat HTTP untuk "
        "kelima peran dan tanpa login di `tests/test_access_matrix.py`.",
        "",
        "Keterangan: ✓ boleh, – ditolak 403. Endpoint selain publik menolak permintaan tanpa "
        "login dengan 401. Pada heatmap, peran dengan `workload:read_own` saja hanya melihat "
        "dirinya; pada daftar task, Anggota Tim hanya melihat task miliknya (DIG-19).",
        "",
        "| Method | Endpoint | Izin | " + " | ".join(labels) + " |",
        "| --- | --- | --- | " + " | ".join("---" for _ in labels) + " |",
    ]
    for rule in access_rules(app):
        if rule.kind == "public":
            needed = "publik"
        elif rule.kind == "login":
            needed = "login"
        else:
            joiner = " atau " if rule.kind == "any_of" else " + "
            needed = joiner.join(f"`{p.value}`" for p in sorted(rule.perms))
        marks = [("✓" if rule.allows(perms) else "–") for perms in roles.values()]
        path = rule.path.removeprefix(API_PREFIX)
        lines.append(f"| {rule.method} | `{path}` | {needed} | " + " | ".join(marks) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    from app.main import app

    parser = argparse.ArgumentParser(description="Matriks akses per peran (DIG-207)")
    parser.add_argument("--write", type=Path, help="tulis ke berkas, bukan ke layar")
    args = parser.parse_args()
    text = markdown(app)
    if args.write:
        args.write.write_text(text, encoding="utf-8")
        print(f"Ditulis ke {args.write}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
