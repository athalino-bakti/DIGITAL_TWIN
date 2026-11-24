"""Konstanta asumsi formula Resource Load Index (DIG-186, provisional).

Semua angka di sini masih asumsi J&C sampai disepakati tWinner (USULAN_FORMULA_RLI.md bagian 5).
Ganti di modul ini saja; logika di `rli.py` tidak perlu disentuh.
"""

from app.modules.data.enums import AbsenceType, Severity, TaskStatus
from app.modules.data.service import ONBOARDING_DAYS

FORMULA_VERSION = "provisional-2026-11"
PROVISIONAL = True

# A1: task yang tidak menambah beban walau penugasannya masih aktif.
UNLOADED_TASK_STATUSES = frozenset({TaskStatus.DROPPED, TaskStatus.ON_HOLD})

# Ketidakhadiran yang mengurangi hari tersedia. rotation_in berarti anggota hadir.
ABSENCE_TYPES = frozenset(
    {
        AbsenceType.PLANNED_LEAVE,
        AbsenceType.SUDDEN_LEAVE,
        AbsenceType.MATERNITY_LEAVE,
        AbsenceType.ROTATION_OUT,
    }
)

# A3: bobot D-08 workload_items (D-08 tidak punya kolom bobot).
OPERATIONAL_WEIGHT = 0.3
TICKET_WEIGHT = {
    Severity.LOW: 0.2,
    Severity.MEDIUM: 0.4,
    None: 0.4,  # severity kosong diperlakukan medium
    Severity.HIGH: 0.6,
    Severity.CRITICAL: 1.0,
}
HOTFIX_WEIGHT = 1.0

# A5: faktor onboarding menurut hari sejak join_date sampai Senin minggu itu.
# (batas atas inklusif, faktor); sesudah ONBOARDING_DAYS faktornya 1,00.
ONBOARDING_STEPS = ((30, 0.50), (ONBOARDING_DAYS, 0.75))

# Kategori heatmap (A6), USULAN_FORMULA_RLI.md bagian 3:
# rendah < 0,50 <= sedang < 0,80 <= penuh <= 1,00 < overload <= 1,20 < overload_berat.
RLI_DECIMALS = 3
OVERLOAD_THRESHOLD = 1.0
UNAVAILABLE = "tidak_tersedia"
# (kode, label, min, max, overload, max inklusif). None = tanpa batas.
CATEGORIES = (
    ("rendah", "Rendah", None, 0.5, False, False),
    ("sedang", "Sedang", 0.5, 0.8, False, False),
    ("penuh", "Penuh", 0.8, 1.0, False, True),
    ("overload", "Overload", 1.0, 1.2, True, True),
    ("overload_berat", "Overload berat", 1.2, None, True, False),
    (UNAVAILABLE, "Tidak tersedia", None, None, False, False),
)
