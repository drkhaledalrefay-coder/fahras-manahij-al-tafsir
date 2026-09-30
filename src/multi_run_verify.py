"""Run v2_verify for every multi-tafsir base that has moves/<annotator>/ folders.

Idempotent: re-running overwrites verified outputs and summary.md with the same
inputs. Bases without a moves/ directory still get an empty summary.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from v2_verify import configure, verify_all  # noqa: E402

TAFSIR_IDS = ("al_tabari", "al_saadi", "al_baghawi")


def main() -> None:
    for tafsir_id in TAFSIR_IDS:
        base = f"data/multi/{tafsir_id}"
        base_path = ROOT / base
        if not (base_path / "windows").is_dir():
            print(f"skip {base}: no windows/")
            continue
        if not (base_path / "markers").is_dir():
            print(f"skip {base}: no markers/ (run v2_markers.py first)")
            continue
        print(f"=== verify --base {base}")
        configure(base)
        verify_all()


if __name__ == "__main__":
    main()
