"""Determinism check: compare two base trees file-by-file (names + sha256).

Usage: python -X utf8 reports/nur/check_determinism.py <dir_a> <dir_b>
Prints file counts and either IDENTICAL or the differing names.
"""
import hashlib
import os
import sys


def tree(d):
    out = {}
    for dp, dn, fn in os.walk(d):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()
            out[os.path.relpath(p, d)] = h
    return out


def main():
    a = tree(sys.argv[1])
    b = tree(sys.argv[2])
    ka = set(a)
    kb = set(b)
    print("files: %d %d" % (len(ka), len(kb)))
    namediff = sorted(ka ^ kb)
    print("name-diff: %s" % (namediff[:10] if namediff else "NONE"))
    contentdiff = sorted([k for k in ka & kb if a[k] != b[k]])
    if not namediff and not contentdiff:
        print("IDENTICAL")
    else:
        print("content-diff: %s" % contentdiff[:10])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
