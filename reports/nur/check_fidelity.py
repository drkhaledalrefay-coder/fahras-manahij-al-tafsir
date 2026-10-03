"""Fidelity check for Surat an-Nur prep (surah 24, 4 tafsirs).

Verifies every window_text (windows/*.json) and every span text
(windows + spans/*.json) under data/nur/<tafsir>/ is a byte-exact
substring of the DB tafsir text for that tafsir+verse.
DB is opened read-only (mode=ro). No tafsir text is printed.
Usage: python -X utf8 reports/nur/check_fidelity.py --db <path>/quran.db
"""
import argparse
import glob
import json
import sqlite3

TABLES = {
    "al_tabari": "tafsir_tabary",
    "ibn_kathir": "tafsir_katheer",
    "al_baghawi": "tafsir_baghawy",
    "al_saadi": "tafsir_saadi",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    try:
        raw = {}
        for tafsir, table in TABLES.items():
            for aya, text in con.execute(
                "SELECT [aya],[tafsir] FROM [%s] WHERE [sura]=24" % table
            ):
                raw[(tafsir, aya)] = str(text)
        total = ok = 0
        bad = []
        for tafsir in TABLES:
            for wf in sorted(glob.glob("data/nur/%s/windows/*.json" % tafsir)):
                w = json.load(open(wf, encoding="utf-8"))
                key = (tafsir, w["ayah_number"])
                total += 1
                if w["window_text"] in raw[key]:
                    ok += 1
                else:
                    bad.append(wf)
                for s in w["spans"]:
                    total += 1
                    if s["text"] in raw[key]:
                        ok += 1
                    else:
                        bad.append("%s#%s" % (wf, s["id"]))
            for sf in sorted(glob.glob("data/nur/%s/spans/*.json" % tafsir)):
                sp = json.load(open(sf, encoding="utf-8"))
                key = (tafsir, sp["ayah_number"])
                for s in sp["spans"]:
                    total += 1
                    if s["text"] in raw[key]:
                        ok += 1
                    else:
                        bad.append("%s#%s" % (sf, s["id"]))
        print("%d/%d exact" % (ok, total))
        if bad:
            print("MISMATCHES:")
            for b in bad[:20]:
                print("  " + b)
            raise SystemExit(1)
    finally:
        con.close()


if __name__ == "__main__":
    main()
