"""STRICT fidelity checker for the An-Nur prep (surah 24, 4 tafsirs)."""
from __future__ import annotations
import argparse
import glob
import hashlib
import json
import sqlite3
from pathlib import Path
HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
DATA_NUR = ROOT / "data" / "nur"
DEFAULT_DB = Path(r"C:\Users\Khale\Documents\Codex\2026-09-28\islamic-ai-contest\_db\quran.db")
EXPECTED_DB_SHA256 = "10e61f615ab5e6a3440e8ecc8ba1dc2273d12cd9048752760fe53a44d191cc27"
TAFSIRS = ("al_tabari", "ibn_kathir", "al_baghawi", "al_saadi")
TABLES = {"al_tabari": "tafsir_tabary", "ibn_kathir": "tafsir_katheer", "al_baghawi": "tafsir_baghawy", "al_saadi": "tafsir_saadi"}
SURAH = 24
AYAT = list(range(1, 65))
ok = 0
total = 0
fails: list[str] = []
def check(cond: bool, msg: str) -> bool:
    global ok, total
    total += 1
    if cond:
        ok += 1
    else:
        fails.append(msg)
    return bool(cond)
def is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)
def read_exact(path: Path) -> tuple[bytes, str]:
    raw = path.read_bytes()
    return raw, raw.decode("utf-8")
def check_span(src: str, s: dict, where: str) -> None:
    sid = s.get("id", "?")
    st, en, tx = s.get("start"), s.get("end"), s.get("text")
    if not check(is_int(st) and is_int(en), f"{where}#{sid}: bad offset types"):
        return
    if not check(0 <= st < en <= len(src), f"{where}#{sid}: offsets out of range"):
        return
    if not check(isinstance(tx, str) and len(tx) > 0, f"{where}#{sid}: empty text"):
        return
    check(src[st:en] == tx, f"{where}#{sid}: position mismatch [{st}:{en}]")
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()
    db_path = Path(args.db)
    if not check(db_path.is_file(), f"DB not found: {db_path}"):
        print(f"STRICT: {ok}/{total} exact")
        return 2
    digest = hashlib.sha256(db_path.read_bytes()).hexdigest()
    if digest != EXPECTED_DB_SHA256:
        print(f"DB sha256 MISMATCH: {digest}")
        print(f"STRICT: {ok}/{total} exact")
        return 2
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    try:
        for tafsir in TAFSIRS:
            f0 = len(fails)
            rows = list(con.execute("SELECT [aya],[tafsir] FROM [%s] WHERE [sura]=%d" % (TABLES[tafsir], SURAH)))
            check(len(rows) == 64, f"{tafsir}: DB row count {len(rows)} != 64")
            check(len(rows) == len({r[0] for r in rows}), f"{tafsir}: duplicate aya rows")
            db_text = {a: (t if isinstance(t, str) else "") for a, t in rows if a in set(AYAT)}
            check(sorted(db_text) == AYAT, f"{tafsir}: DB ayat != 24:1..24:64")
            for a in AYAT:
                check(db_text.get(a) is not None and len(db_text.get(a, "")) > 0, f"{tafsir}: empty DB 24:{a}")
            sfs = sorted(glob.glob(str(DATA_NUR / tafsir / "spans" / "*.json")))
            wfs = sorted(glob.glob(str(DATA_NUR / tafsir / "windows" / "*.json")))
            if not sfs or not wfs:
                print(f"ABORT {tafsir}: 0 files (spans={len(sfs)} windows={len(wfs)})")
                print(f"STRICT: {ok}/{total} exact")
                return 2
            verses = wins = spans_n = gaps = 0
            for a in AYAT:
                rf = DATA_NUR / tafsir / "raw" / f"24_{a}.txt"
                if not check(rf.is_file(), f"{tafsir}: missing raw 24_{a}.txt"):
                    continue
                rb, rt = read_exact(rf)
                if check(rt == db_text.get(a), f"{tafsir}: raw!=DB 24:{a}"):
                    verses += 1
            for sf in sfs:
                sp = json.loads(Path(sf).read_bytes().decode("utf-8"))
                rb, src = read_exact(ROOT / sp["source_file"])
                check(hashlib.sha256(rb).hexdigest() == sp["source_sha256"], f"{tafsir}: spans sha mismatch {Path(sf).name}")
                for s in sp["spans"]:
                    spans_n += 1
                    check_span(src, s, f"{tafsir}/spans/{Path(sf).name}")
            for wf in wfs:
                wins += 1
                w = json.loads(Path(wf).read_bytes().decode("utf-8"))
                wn = f"{tafsir}/windows/{Path(wf).name}"
                rb, src = read_exact(ROOT / w["source_file"])
                check(hashlib.sha256(rb).hexdigest() == w["source_sha256"], f"{wn}: sha mismatch")
                ws, we, wt = w.get("window_start"), w.get("window_end"), w.get("window_text")
                if not check(is_int(ws) and is_int(we), f"{wn}: bad window offsets"):
                    continue
                if not check(0 <= ws < we <= len(src), f"{wn}: window out of range"):
                    continue
                if not check(isinstance(wt, str) and len(wt) > 0, f"{wn}: empty window_text"):
                    continue
                check(src[ws:we] == wt, f"{wn}: window position mismatch [{ws}:{we}]")
                pe = None
                ps = None
                ordered = True
                for s in w["spans"]:
                    spans_n += 1
                    check_span(src, s, wn)
                    if is_int(s.get("start")) and is_int(s.get("end")):
                        if ps is not None and s["start"] < ps:
                            ordered = False
                        if pe is not None:
                            if s["start"] < pe:
                                check(False, f"{wn}#{s.get('id')}: overlap")
                            elif s["start"] > pe:
                                gaps += 1
                        ps, pe = s["start"], s["end"]
                check(ordered, f"{wn}: spans out of order")
            print(f"{tafsir}: verses={verses}/64 windows={wins} spans={spans_n} gaps={gaps} failures={len(fails) - f0}")
    finally:
        con.close()
    for b in fails[:20]:
        print("FAIL " + b)
    print(f"STRICT: {ok}/{total} exact")
    return 1 if fails else 0
if __name__ == "__main__":
    raise SystemExit(main())
