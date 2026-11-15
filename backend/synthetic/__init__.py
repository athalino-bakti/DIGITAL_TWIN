"""Generator data sintetis Digital Twin PuTI (DIG-16).

Satu "dunia simulasi" Tim DEVTI dibangun dari seed yang sama, lalu ditulis sebagai
11 CSV final sources sesuai Data Dictionary (DIG-81), sumber mentah Project Plan,
ekspor JSON Trello, dan git log (DIG-82), serta versi kotornya (DIG-83).

Seluruh nama orang, proyek, dan kejadian adalah fiktif. Skenario kerjanya mengikuti
hasil wawancara dengan Tim DEVTI PuTI. Jalankan dari folder backend:

    python -m synthetic --out synthetic-output --seed 42 --as-of 2026-11-06 --dirty
"""

from synthetic.world import World, build_world

__all__ = ["World", "build_world"]
