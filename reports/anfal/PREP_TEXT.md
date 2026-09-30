# Anfal source-text prep — 2026-09-30

**DB sha256:** `10e61f615ab5e6a3440e8ecc8ba1dc2273d12cd9048752760fe53a44d191cc27` — **MATCH** (`docs/RUN.md` / `data/raw/manifest.json`). Opened read-only: `file:<path-to>/quran.db?mode=ro`. `quran.db` not in repo; `data/anfal/` not gitignored (`git check-ignore` exit 1).

**Flag gaps (src/ not edited):** `multi_fetch.py` has only `--db` (hardcodes 2:255/2:102/17:105 → `data/raw`); `multi_layers` / `multi_spans` / `multi_windows` have no `--base`/`--surah` (hardcode `data/multi` + those ayat). Prep reused their functions into `data/anfal/<tafsir>/`. `v2_markers` / `v2_packets` accept `--base`. `run_window.py` has no `--base` (maps tafsir → `data/multi` / `data/v2` only). `run_surah.py` absent.

**Commands run:** DB hash check → extract+layers+spans+windows (surah 8, paragraph-pack cap 110 for long verses) → `v2_markers.py` / `v2_packets.py` with `--base data/anfal/<tafsir>` and Arabic `--tafsir-name`. Stopped before classification. No model calls.

| tafsir | verses/75 | windows | chars | missing |
|---|---:|---:|---:|---|
| al_tabari | 75 | 97 | 434662 | — |
| ibn_kathir | 75 | 78 | 322965 | — |
| al_baghawi | 75 | 75 | 166559 | — |
| al_saadi | 75 | 75 | 57928 | — |

**Coverage:** 75×4 = 300 verses. **Windows:** 325. **Fidelity:** 325/325 = **100%** (each `window_text` + span is a byte-exact substring of DB text). **Largest window:** `al_baghawi/8_41` = 15097 chars.

**Day-4 classify (dry-run first) — needs `--base` on `run_window.py` first:**
```bash
python src/run_window.py --tafsir al_tabari --window 8_2 --base data/anfal/al_tabari --dry-run
python src/run_window.py --tafsir al_tabari --window 8_2 --base data/anfal/al_tabari --api
# all windows (after --base): for each packets/*.json under data/anfal/al_tabari
python src/run_window.py --tafsir al_tabari --window <id> --base data/anfal/al_tabari --dry-run
```
**Blocker for day 4:** add `--base` to `run_window.py` (or `run_surah.py`) so packets resolve under `data/anfal/`.
