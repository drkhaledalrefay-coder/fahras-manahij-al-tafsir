"""Checkpoint B: rebuild annotated units from pinned source, validate, compare two annotators, build specialist queue."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AYAT = ["17_105", "2_255", "2_102"]
ANNOTATORS = ["grok", "codex"]
SENSITIVE = {"C_ISRAILIYYAT", "C_TAKHRIJ", "C_FIQH", "C_NUZUL"}
LOW_CONF = 0.6


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def taxonomy_ids():
    return set(re.findall(r"\|\s*([SC]_[A-Z]+)\s*\|", (ROOT / "method/taxonomy.md").read_text(encoding="utf-8")))


def manifest_hash(ayah):
    m = load(ROOT / "data/raw/manifest.json")
    hits = []

    def walk(x):
        if isinstance(x, dict):
            p = str(x.get("path") or x.get("file") or x.get("local_path") or "").replace("\\", "/")
            if p.endswith(f"tafsircenter/{ayah}.txt") and x.get("sha256"):
                hits.append(x["sha256"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(m)
    return hits[0] if hits else None


def validate(ayah, spans, ann, valid_ids):
    errs = []
    order = [s["id"] for s in spans]
    pos = {sid: i for i, sid in enumerate(order)}
    seen = []
    for u in ann["units"]:
        ids = u["span_ids"]
        if any(i not in pos for i in ids):
            errs.append(f"{u['unit_id']}: unknown span id")
            continue
        idx = [pos[i] for i in ids]
        if idx != list(range(idx[0], idx[0] + len(idx))):
            errs.append(f"{u['unit_id']}: spans not consecutive")
        seen.extend(ids)
        for t in u.get("source_tags", []) + u.get("content_tags", []):
            if t not in valid_ids:
                errs.append(f"{u['unit_id']}: invalid tag {t}")
        if not u.get("source_tags") or not u.get("content_tags"):
            errs.append(f"{u['unit_id']}: missing a tag layer")
    if seen != order:
        missing = set(order) - set(seen)
        dup = {s for s in seen if seen.count(s) > 1}
        errs.append(f"coverage error: missing={sorted(missing)[:5]} dup={sorted(dup)[:5]} order_ok={seen == [s for s in order if s in seen]}")
    return errs


def rebuild(src, spans_by_id, unit):
    first, last = spans_by_id[unit["span_ids"][0]], spans_by_id[unit["span_ids"][-1]]
    parts = "".join(spans_by_id[i]["text"] for i in unit["span_ids"])
    ok = all(src[spans_by_id[i]["start"]:spans_by_id[i]["end"]] == spans_by_id[i]["text"] for i in unit["span_ids"])
    return {"start": first["start"], "end": last["end"], "text": parts, "verbatim_ok": ok}


def span_labels(ann):
    out = {}
    for u in ann["units"]:
        for i, sid in enumerate(u["span_ids"]):
            out[sid] = {
                "unit": u["unit_id"],
                "S": frozenset(u.get("source_tags", [])),
                "C": frozenset(u.get("content_tags", [])),
                "conf": float(u.get("confidence", 0)),
                "is_last": i == len(u["span_ids"]) - 1,
                "reason": u.get("reason_ar", ""),
            }
    return out


def jacc(a, b):
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def main():
    valid_ids = taxonomy_ids()
    report = {"ayat": {}, "totals": {}}
    queue = []
    md = ["# Checkpoint B — rebuild, validation, inter-annotator comparison\n"]
    tot = {"spans": 0, "S_exact": 0, "C_exact": 0, "both_exact": 0, "queue_spans": 0}

    for ayah in AYAT:
        raw = (ROOT / f"data/raw/tafsircenter/{ayah}.txt").read_bytes()
        sha_now = hashlib.sha256(raw).hexdigest()
        sha_pinned = manifest_hash(ayah)
        src = raw.decode("utf-8")
        spans = load(ROOT / f"data/spans_pilot/{ayah}.json")
        spans = spans["spans"] if isinstance(spans, dict) else spans
        by_id = {s["id"]: s for s in spans}
        anns = {a: load(ROOT / f"data/tags/{a}/{ayah}.json") for a in ANNOTATORS}

        r = {"source_sha256_matches_manifest": sha_now == sha_pinned, "spans": len(spans), "annotators": {}}
        for a, ann in anns.items():
            errs = validate(ayah, spans, ann, valid_ids)
            units = [rebuild(src, by_id, u) for u in ann["units"] if all(i in by_id for i in u["span_ids"])]
            r["annotators"][a] = {
                "units": len(ann["units"]),
                "validation_errors": errs,
                "all_units_verbatim": all(u["verbatim_ok"] for u in units),
                "low_conf_units": sum(1 for u in ann["units"] if float(u.get("confidence", 0)) < LOW_CONF),
            }

        la, lb = span_labels(anns["grok"]), span_labels(anns["codex"])
        order = [s["id"] for s in spans]
        ba = {s for s in order[:-1] if la.get(s, {}).get("is_last")}
        bb = {s for s in order[:-1] if lb.get(s, {}).get("is_last")}
        inter = len(ba & bb)
        prec = inter / len(bb) if bb else 1.0
        rec = inter / len(ba) if ba else 1.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

        s_ex = c_ex = both = 0
        sj = cj = 0.0
        qcount = 0
        for sid in order:
            x, y = la.get(sid), lb.get(sid)
            if not x or not y:
                continue
            se, ce = x["S"] == y["S"], x["C"] == y["C"]
            s_ex += se
            c_ex += ce
            both += se and ce
            sj += jacc(x["S"], y["S"])
            cj += jacc(x["C"], y["C"])
            why = []
            if not (se and ce):
                why.append("disagreement")
            if min(x["conf"], y["conf"]) < LOW_CONF:
                why.append("low_confidence")
            if (x["C"] | y["C"]) & SENSITIVE:
                why.append("sensitive_tag")
            if why:
                qcount += 1
                queue.append({
                    "ayah": ayah.replace("_", ":"), "span_id": sid,
                    "start": by_id[sid]["start"], "end": by_id[sid]["end"],
                    "text": by_id[sid]["text"], "why": why,
                    "grok": {"S": sorted(x["S"]), "C": sorted(x["C"]), "conf": x["conf"], "reason": x["reason"]},
                    "codex": {"S": sorted(y["S"]), "C": sorted(y["C"]), "conf": y["conf"], "reason": y["reason"]},
                })
        n = len(order)
        r["agreement"] = {
            "boundary_f1": round(f1, 3), "boundaries_grok": len(ba), "boundaries_codex": len(bb), "boundaries_shared": inter,
            "span_source_exact": round(s_ex / n, 3), "span_content_exact": round(c_ex / n, 3), "span_both_exact": round(both / n, 3),
            "span_source_jaccard": round(sj / n, 3), "span_content_jaccard": round(cj / n, 3),
            "specialist_queue_spans": qcount, "auto_accept_spans": n - qcount,
        }
        report["ayat"][ayah] = r
        tot["spans"] += n
        tot["S_exact"] += s_ex
        tot["C_exact"] += c_ex
        tot["both_exact"] += both
        tot["queue_spans"] += qcount

        ag = r["agreement"]
        md.append(f"## {ayah.replace('_', ':')}\n")
        md.append(f"- Source sha256 matches pinned manifest: **{r['source_sha256_matches_manifest']}**")
        for a, info in r["annotators"].items():
            md.append(f"- {a}: {info['units']} units · verbatim rebuild OK: **{info['all_units_verbatim']}** · validation errors: {len(info['validation_errors'])} {info['validation_errors'][:3]} · low-confidence units: {info['low_conf_units']}")
        md.append(f"- Boundary agreement F1: **{ag['boundary_f1']}** (grok {ag['boundaries_grok']}, codex {ag['boundaries_codex']}, shared {ag['boundaries_shared']})")
        md.append(f"- Span-level exact agreement — source tags: **{ag['span_source_exact']}**, content tags: **{ag['span_content_exact']}**, both: **{ag['span_both_exact']}**")
        md.append(f"- Specialist queue: **{qcount}/{n} spans**; auto-accept candidates: {n - qcount}\n")

    t = tot["spans"]
    report["totals"] = {
        "spans": t, "span_source_exact": round(tot["S_exact"] / t, 3), "span_content_exact": round(tot["C_exact"] / t, 3),
        "span_both_exact": round(tot["both_exact"] / t, 3), "specialist_queue_spans": tot["queue_spans"],
    }
    md.append("## Totals\n")
    md.append("```\n" + json.dumps(report["totals"], ensure_ascii=False, indent=1) + "\n```")
    (ROOT / "reports/comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "reports/comparison.md").write_text("\n".join(md), encoding="utf-8")
    (ROOT / "reports/specialist_queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
