# Nur source-text prep — 2026-10-03

**DB sha256:** `10e61f615ab5e6a3440e8ecc8ba1dc2273d12cd9048752760fe53a44d191cc27` — **MATCH** (`docs/RUN.md` / task spec). Opened read-only: `file:<path-to>/quran.db?mode=ro`. `quran.db` not in repo; `data/nur/` not gitignored (`git check-ignore` exit 1).

**Procedure:** same as al-Anfal (`reports/anfal/PREP_TEXT.md`, commit 288b098): `--dry-run` preview on al_tabari first, then one full `run_surah.py` per tafsir (surah 24, `--base data/nur/<tafsir>`), never `--classify`. Stopped before classification. No model calls. `src/`, `schema/`, `method/`, `web/` untouched.

**Commands run:**

```bash
python src/run_surah.py --db "<DB>" --tafsir al_tabari  --surah 24 --base data/nur/al_tabari --dry-run
python src/run_surah.py --db "<DB>" --tafsir al_tabari  --surah 24 --base data/nur/al_tabari
python src/run_surah.py --db "<DB>" --tafsir ibn_kathir --surah 24 --base data/nur/ibn_kathir
python src/run_surah.py --db "<DB>" --tafsir al_baghawi --surah 24 --base data/nur/al_baghawi
python src/run_surah.py --db "<DB>" --tafsir al_saadi   --surah 24 --base data/nur/al_saadi
```

| tafsir | verses/64 | windows | chars | missing |
|---|---:|---:|---:|---|
| al_tabari | 64 | 84 | 353792 | — |
| ibn_kathir | 64 | 82 | 294611 | — |
| al_baghawi | 64 | 66 | 190316 | — |
| al_saadi | 64 | 64 | 73585 | — |

**Coverage:** 64×4 = 256 verses, 0 missing. **Windows:** 296. **Largest window:** `al_baghawi/24_7` = 17328 chars.

**Fidelity:** 18786/18786 = **100%** — every `window_text` and every span text (windows + spans files) under `data/nur/**` is a byte-exact substring of the DB text for that tafsir+verse. Check: `python -X utf8 reports/nur/check_fidelity.py --db "<DB>"` (DB opened `mode=ro`).

**Determinism:** re-ran al_saadi into `data/nur/_tmp_rerun_saadi` (temp dir, removed after): 384 vs 384 files, same names; all content identical except the expected `source_file` path prefix (`data/nur/al_saadi/...` vs `data/nur/_tmp_rerun_saadi/...`) — 320/320 compared files equal after normalizing that field; `raw/`, `markers/` byte-identical.

**No model:** `LLM_API_KEY` unset in this shell; no `moves/` or `verified/` folders under `data/nur/`; `--classify` never passed.

**Status:** `git status --short` shows only `?? data/nur/` and `?? reports/nur/` (uncommitted per task). `du -sh data/nur` = 22M. Not committed.
