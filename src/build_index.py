"""Build searchable Tafsir Index demo data and single-file HTML page."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from normalize import l1_normalize  # noqa: E402

AYAT = ["17_105", "2_255", "2_102"]
SENSITIVE = {"C_ISRAILIYYAT", "C_TAKHRIJ", "C_FIQH", "C_NUZUL"}
LOW_CONF = 0.6

AYAH_META = {
    "17_105": {
        "ayah": "17:105",
        "surah": 17,
        "ayah_number": 105,
        "label_ar": "الإسراء ١٠٥",
        "surah_name_ar": "الإسراء",
    },
    "2_255": {
        "ayah": "2:255",
        "surah": 2,
        "ayah_number": 255,
        "label_ar": "البقرة ٢٥٥",
        "surah_name_ar": "البقرة",
    },
    "2_102": {
        "ayah": "2:102",
        "surah": 2,
        "ayah_number": 102,
        "label_ar": "البقرة ١٠٢",
        "surah_name_ar": "البقرة",
    },
}

# Arabic label from taxonomy + plain rewording for non-specialists (≤12 words).
TAG_INFO = {
    "S_QURAN": {
        "label_ar": "تفسير القرآن بالقرآن",
        "explain_ar": "يشرح الآية بآية أخرى من القرآن",
        "layer": "source",
    },
    "S_SUNNAH": {
        "label_ar": "تفسير القرآن بالسنة",
        "explain_ar": "يستدل بحديث عن النبي صلى الله عليه وسلم",
        "layer": "source",
    },
    "S_SAHABA": {
        "label_ar": "أقوال الصحابة",
        "explain_ar": "ينقل قولاً لصحابي يبيّن معنى الآية",
        "layer": "source",
    },
    "S_TABIIN": {
        "label_ar": "أقوال التابعين",
        "explain_ar": "ينقل قولاً لتابعي يبيّن معنى الآية",
        "layer": "source",
    },
    "S_LUGHA": {
        "label_ar": "اللغة",
        "explain_ar": "يوضّح معنى الألفاظ من جهة اللغة",
        "layer": "source",
    },
    "S_RAY": {
        "label_ar": "الاجتهاد والرأي",
        "explain_ar": "تحليل من المفسّر نفسه لمعنى الآية",
        "layer": "source",
    },
    "S_IRAB": {
        "label_ar": "الإعراب",
        "explain_ar": "يبين الموقع النحوي لألفاظ الآية",
        "layer": "source",
    },
    "C_NUZUL": {
        "label_ar": "أسباب النزول",
        "explain_ar": "يذكر سبب نزول الآية أو سياقه",
        "layer": "content",
    },
    "C_FIQH": {
        "label_ar": "فقه وأحكام",
        "explain_ar": "يستنبط حكماً شرعياً من الآية",
        "layer": "content",
    },
    "C_BALAGHA": {
        "label_ar": "بلاغة",
        "explain_ar": "يشير إلى أسلوب بلاغي في الآية",
        "layer": "content",
    },
    "C_SHIR": {
        "label_ar": "شعر",
        "explain_ar": "يستشهد ببيت شعر للتوضيح",
        "layer": "content",
    },
    "C_ISRAILIYYAT": {
        "label_ar": "إسرائيليات",
        "explain_ar": "مادة منسوبة إلى كتب بني إسرائيل",
        "layer": "content",
    },
    "C_FADAIL": {
        "label_ar": "فضائل القرآن/الآية",
        "explain_ar": "يذكر فضل هذه الآية أو السورة",
        "layer": "content",
    },
    "C_TAKHRIJ": {
        "label_ar": "تخريج/حكم حديثي",
        "explain_ar": "يحكم على سند الحديث أو مصدره",
        "layer": "content",
    },
    "C_TAFSIR": {
        "label_ar": "بيان معنى",
        "explain_ar": "شرح مباشر لمعنى الآية أو ألفاظها",
        "layer": "content",
    },
}

DATA_MARKER = "__INDEX_DATA_JSON__"


def _read_json(path: Path):
    return json.loads(path.read_bytes().decode("utf-8"))


def _read_source_text(path: Path) -> tuple[str, bytes, str]:
    """Read pinned source without newline translation; return text, raw bytes, sha256."""
    raw = path.read_bytes()
    # Equivalent to open(..., encoding='utf-8', newline=''): no CRLF rewriting.
    text = raw.decode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    return text, raw, sha


def _manifest_sha(manifest: dict, ayah_key: str) -> str | None:
    hits: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            p = str(node.get("path") or "").replace("\\", "/")
            if p.endswith(f"tafsircenter/{ayah_key}.txt") and node.get("sha256"):
                hits.append(node["sha256"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(manifest)
    return hits[0] if hits else None


def _cover_map(units: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for u in units:
        for sid in u["span_ids"]:
            out[sid] = u
    return out


def _display_span_groups(spans: list[dict], units_a: list[dict], units_b: list[dict]) -> list[list[str]]:
    """Union of annotator boundaries: new unit wherever either annotator starts."""
    order = [s["id"] for s in spans]
    starts: set[str] = set()
    for units in (units_a, units_b):
        for u in units:
            starts.add(u["span_ids"][0])
    groups: list[list[str]] = []
    current: list[str] = []
    for sid in order:
        if sid in starts and current:
            groups.append(current)
            current = []
        current.append(sid)
    if current:
        groups.append(current)
    return groups


def _tags_equal(a: list[str], b: list[str]) -> bool:
    return sorted(a) == sorted(b)


def _status_for(unit_a: dict, unit_b: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    same_source = _tags_equal(unit_a.get("source_tags", []), unit_b.get("source_tags", []))
    same_content = _tags_equal(unit_a.get("content_tags", []), unit_b.get("content_tags", []))
    if not (same_source and same_content):
        reasons.append("اختلاف بين الفاحصين")
    conf_a = float(unit_a.get("confidence", 0))
    conf_b = float(unit_b.get("confidence", 0))
    if conf_a < LOW_CONF or conf_b < LOW_CONF:
        reasons.append("ثقة منخفضة")
    content_union = set(unit_a.get("content_tags", [])) | set(unit_b.get("content_tags", []))
    if content_union & SENSITIVE:
        reasons.append("وسم حساس")
    if (
        same_source
        and same_content
        and conf_a >= LOW_CONF
        and conf_b >= LOW_CONF
        and not (content_union & SENSITIVE)
    ):
        return "agreed", []
    return "needs_review", reasons


def _l1_words(text: str) -> list[str]:
    norm = l1_normalize(text)
    return norm.split() if norm else []


def _letter_edit_distance(a: str, b: str) -> int:
    """Levenshtein distance at Unicode letter/codepoint level."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _best_b_window(a_words: list[str], b_words: list[str]) -> list[str]:
    """Align A to B via largest matching block; take a window of len(A)+10 words."""
    if not a_words:
        return []
    if not b_words:
        return []
    win_size = len(a_words) + 10
    sm = SequenceMatcher(None, a_words, b_words, autojunk=False)
    blocks = [blk for blk in sm.get_matching_blocks() if blk.size > 0]
    if blocks:
        best = max(blocks, key=lambda blk: blk.size)
        # Align A[0] with B[best.b - best.a] when possible.
        win_start = max(0, best.b - best.a)
    else:
        # Fallback: window with best quick_ratio.
        win_start = 0
        best_r = -1.0
        last = max(0, len(b_words) - 1)
        step = max(1, len(a_words) // 4 or 1)
        matcher = SequenceMatcher()
        matcher.set_seq2(a_words)
        for i in range(0, last + 1, step):
            window = b_words[i : i + win_size]
            matcher.set_seq1(window)
            r = matcher.quick_ratio()
            if r > best_r:
                best_r = r
                win_start = i
    win_end = min(len(b_words), win_start + win_size)
    if win_end - win_start < win_size:
        win_start = max(0, win_end - win_size)
    return b_words[win_start:win_end]


def _trim_edge_inserts(
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[tuple[str, int, int, int, int]]:
    """Drop leading/trailing pure insert opcodes (B context outside the unit)."""
    ops = list(opcodes)
    while ops and ops[0][0] == "insert":
        ops.pop(0)
    while ops and ops[-1][0] == "insert":
        ops.pop()
    return ops


def _classify_cross_source_diffs(
    a_words: list[str], b_window: list[str]
) -> tuple[list[dict], str, float]:
    """Return (diffs, cross_source class, match_ratio) for A words vs aligned B window."""
    sm = SequenceMatcher(None, a_words, b_window, autojunk=False)
    match_ratio = round(sm.ratio(), 4)
    ops = _trim_edge_inserts(sm.get_opcodes())
    diffs: list[dict] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        a_part = a_words[i1:i2]
        b_part = b_window[j1:j2]
        if tag == "replace":
            kind = "variant"
        elif tag == "delete":
            kind = "missing_in_b"
        else:  # insert (internal only after trim)
            kind = "extra_in_b"
        diffs.append({"kind": kind, "a_words": a_part, "b_words": b_part})

    if not diffs:
        return diffs, "identical", match_ratio

    only_small_variants = all(
        d["kind"] == "variant" and len(d["a_words"]) <= 2 and len(d["b_words"]) <= 2 for d in diffs
    )
    if only_small_variants and len(diffs) <= 4:
        return diffs, "minor", match_ratio
    return diffs, "different", match_ratio


def _is_suspect_typo(a_words: list[str], b_words: list[str], b_vocab: set[str]) -> bool:
    """Generic digital-typo heuristic: 1-letter variant or missing-space merge in A."""
    if not a_words or not b_words:
        return False
    # Missing space in A: one fused A token equals concatenation of B tokens.
    if len(a_words) == 1 and len(b_words) >= 2 and a_words[0] == "".join(b_words):
        return all(w in b_vocab for w in b_words)
    # One-letter-off single-word variant (B form attested in Source B).
    if len(a_words) == 1 and len(b_words) == 1:
        aw, bw = a_words[0], b_words[0]
        if bw in b_vocab and _letter_edit_distance(aw, bw) == 1:
            return True
    # Same with joined sides when replace spans a short phrase (e.g. split/merge).
    a_join = "".join(a_words)
    b_join = "".join(b_words)
    if a_join != b_join and _letter_edit_distance(a_join, b_join) == 1:
        if all(w in b_vocab for w in b_words):
            return True
    return False


def _cross_source_for_unit(unit_text: str, src_b: str) -> dict:
    a_words = _l1_words(unit_text)
    b_words = _l1_words(src_b)
    b_window = _best_b_window(a_words, b_words)
    diffs, cross_source, match_ratio = _classify_cross_source_diffs(a_words, b_window)
    return {
        "cross_source": cross_source,
        "match_ratio": match_ratio,
        "diffs": diffs,
        "in_source_b": cross_source == "identical",
    }


def _annotator_payload(unit: dict) -> dict:
    return {
        "source_tags": list(unit.get("source_tags", [])),
        "content_tags": list(unit.get("content_tags", [])),
        "confidence": float(unit.get("confidence", 0)),
        "reason_ar": unit.get("reason_ar", ""),
    }


def _apparatus_in_window(src_a: str, layers: dict, win_start: int, win_end: int) -> list[dict]:
    out: list[dict] = []
    for r in layers.get("ranges", []):
        layer = r.get("layer")
        if layer not in ("footnote", "editor_bracket"):
            continue
        start, end = int(r["start"]), int(r["end"])
        if end <= win_start or start >= win_end:
            continue
        # Clip to pilot window so we only show apparatus inside the demo window.
        clip_s = max(start, win_start)
        clip_e = min(end, win_end)
        if clip_e <= clip_s:
            continue
        out.append(
            {
                "start": clip_s,
                "end": clip_e,
                "layer": layer,
                "text": src_a[clip_s:clip_e],
            }
        )
    return out


def _summary_from_reports(comparison: dict, recon: dict) -> dict:
    totals = comparison["totals"]
    after = {}
    for row in recon.get("ayahs", []):
        key = f"{row['surah']}_{row['ayah_number']}"
        after[key] = {
            "ratio": row["similarity_ratio_l1_after"],
            "pct": round(row["similarity_ratio_l1_after"] * 100, 1),
            "label_ar": AYAH_META[key]["label_ar"],
        }
    return {
        "total_spans": totals["spans"],
        "verbatim_pct": 100.0,
        "source_tag_agreement": totals["span_source_exact"],
        "source_tag_agreement_pct": round(totals["span_source_exact"] * 100, 1),
        "content_tag_agreement": totals["span_content_exact"],
        "content_tag_agreement_pct": round(totals["span_content_exact"] * 100, 1),
        "cross_source_after": after,
        "source_a_suspect_typos": [],
    }


def _collect_suspect_typos(ayat: list[dict], src_b_by_ayah: dict[str, str]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for a in ayat:
        b_vocab = set(_l1_words(src_b_by_ayah[a["id"]]))
        for u in a["units"]:
            for d in u.get("diffs", []):
                if d["kind"] != "variant":
                    continue
                aw, bw = d["a_words"], d["b_words"]
                if not _is_suspect_typo(aw, bw, b_vocab):
                    continue
                a_disp = " ".join(aw)
                b_disp = " ".join(bw)
                key = (a["id"], a_disp, b_disp)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "ayah_id": a["id"],
                        "ayah_label_ar": a["label_ar"],
                        "unit_id": u["id"],
                        "a_word": a_disp,
                        "b_word": b_disp,
                        "a_words": list(aw),
                        "b_words": list(bw),
                    }
                )
    return out


def build_ayah(ayah_key: str, manifest: dict) -> dict:
    meta = AYAH_META[ayah_key]
    path_a = ROOT / "data" / "raw" / "tafsircenter" / f"{ayah_key}.txt"
    path_b = ROOT / "data" / "raw" / "quran_com" / f"{ayah_key}.txt"
    src_a, _raw_a, sha_now = _read_source_text(path_a)
    src_b, _, _ = _read_source_text(path_b)
    sha_pinned = _manifest_sha(manifest, ayah_key)
    file_sha_ok = sha_now == sha_pinned

    spans_payload = _read_json(ROOT / "data" / "spans_pilot" / f"{ayah_key}.json")
    spans = spans_payload["spans"]
    by_id = {s["id"]: s for s in spans}

    tags_a = _read_json(ROOT / "data" / "tags" / "grok" / f"{ayah_key}.json")
    tags_b = _read_json(ROOT / "data" / "tags" / "codex" / f"{ayah_key}.json")
    cover_a = _cover_map(tags_a["units"])
    cover_b = _cover_map(tags_b["units"])
    groups = _display_span_groups(spans, tags_a["units"], tags_b["units"])

    win_start = spans[0]["start"]
    win_end = spans[-1]["end"]
    layers = _read_json(ROOT / "data" / "layers" / f"{ayah_key}.json")
    apparatus = _apparatus_in_window(src_a, layers, win_start, win_end)

    units_out: list[dict] = []
    for i, span_ids in enumerate(groups, start=1):
        unit_spans = [by_id[sid] for sid in span_ids]
        offsets = [[s["start"], s["end"]] for s in unit_spans]
        texts = []
        span_ok = True
        for s in unit_spans:
            sliced = src_a[s["start"] : s["end"]]
            if sliced != s["text"]:
                span_ok = False
                raise AssertionError(
                    f"{ayah_key} span {s['id']}: src_a[{s['start']}:{s['end']}] != span text"
                )
            texts.append(s["text"])
        text = "".join(texts)
        # Forbidden: src_a[first.start:last.end] — gaps may hold editor apparatus.
        assert text == "".join(s["text"] for s in unit_spans)

        ua = cover_a[span_ids[0]]
        ub = cover_b[span_ids[0]]
        # Covering unit must include all spans of this display unit.
        for sid in span_ids:
            assert cover_a[sid]["unit_id"] == ua["unit_id"]
            assert cover_b[sid]["unit_id"] == ub["unit_id"]

        status, reasons = _status_for(ua, ub)
        assert status != "approved"

        xs = _cross_source_for_unit(text, src_b)

        same_tags = _tags_equal(ua.get("source_tags", []), ub.get("source_tags", [])) and _tags_equal(
            ua.get("content_tags", []), ub.get("content_tags", [])
        )
        display_mode = "shared" if status == "agreed" and same_tags else "side_by_side"

        units_out.append(
            {
                "id": f"{ayah_key}_d{i:02d}",
                "ayah_id": ayah_key,
                "span_ids": span_ids,
                "offsets": offsets,
                "start": unit_spans[0]["start"],
                "end": unit_spans[-1]["end"],
                "text": text,
                "status": status,
                "reasons": reasons,
                "verbatim_ok": bool(span_ok and file_sha_ok),
                "in_source_b": xs["in_source_b"],
                "cross_source": xs["cross_source"],
                "match_ratio": xs["match_ratio"],
                "diffs": xs["diffs"],
                "tags_display": display_mode,
                "source_tags": list(ua.get("source_tags", [])) if display_mode == "shared" else [],
                "content_tags": list(ua.get("content_tags", [])) if display_mode == "shared" else [],
                "annotators": {
                    "first": _annotator_payload(ua),
                    "second": _annotator_payload(ub),
                },
            }
        )

    return {
        "id": ayah_key,
        "ayah": meta["ayah"],
        "surah": meta["surah"],
        "ayah_number": meta["ayah_number"],
        "label_ar": meta["label_ar"],
        "surah_name_ar": meta["surah_name_ar"],
        "window_start": win_start,
        "window_end": win_end,
        "source_sha256_ok": file_sha_ok,
        "apparatus": apparatus,
        "units": units_out,
        "_src_b": src_b,  # stripped before write
    }


def build_index_data() -> dict:
    manifest = _read_json(ROOT / "data" / "raw" / "manifest.json")
    comparison = _read_json(ROOT / "reports" / "comparison.json")
    recon = _read_json(ROOT / "reports" / "reconciliation_author.json")
    ayat = [build_ayah(k, manifest) for k in AYAT]
    src_b_by_ayah = {a["id"]: a.pop("_src_b") for a in ayat}
    summary = _summary_from_reports(comparison, recon)
    summary["source_a_suspect_typos"] = _collect_suspect_typos(ayat, src_b_by_ayah)
    return {
        "title_ar": "فهرس تفسير ابن كثير — نموذج تجريبي",
        "summary": summary,
        "tags": TAG_INFO,
        "ayat": ayat,
        "annotator_labels": {
            "first": "الفاحص الأول",
            "second": "الفاحص الثاني",
        },
    }


def write_outputs(data: dict) -> tuple[Path, Path]:
    web = ROOT / "web"
    web.mkdir(parents=True, exist_ok=True)
    json_path = web / "index_data.json"
    html_path = web / "index.html"
    template_path = ROOT / "src" / "index_template.html"

    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    json_path.write_text(json_text + "\n", encoding="utf-8", newline="\n")

    template = template_path.read_text(encoding="utf-8")
    if DATA_MARKER not in template:
        raise SystemExit(f"Template missing marker {DATA_MARKER}")
    # Prevent </script> breakout when inlining JSON.
    embedded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    html = template.replace(DATA_MARKER, embedded)
    html_path.write_text(html, encoding="utf-8", newline="\n")
    return json_path, html_path


def main() -> int:
    data = build_index_data()
    json_path, html_path = write_outputs(data)

    n_units = sum(len(a["units"]) for a in data["ayat"])
    n_agreed = sum(1 for a in data["ayat"] for u in a["units"] if u["status"] == "agreed")
    n_review = sum(1 for a in data["ayat"] for u in a["units"] if u["status"] == "needs_review")
    assert all(u["verbatim_ok"] for a in data["ayat"] for u in a["units"])
    assert all(u["status"] != "approved" for a in data["ayat"] for u in a["units"])
    assert all(u["cross_source"] in ("identical", "minor", "different") for a in data["ayat"] for u in a["units"])

    print(f"Wrote {json_path.relative_to(ROOT)} and {html_path.relative_to(ROOT)}")
    print(f"display_units={n_units} agreed={n_agreed} needs_review={n_review}")
    xs_tot = {"identical": 0, "minor": 0, "different": 0}
    for a in data["ayat"]:
        st: dict[str, int] = {}
        xs: dict[str, int] = {"identical": 0, "minor": 0, "different": 0}
        for u in a["units"]:
            st[u["status"]] = st.get(u["status"], 0) + 1
            xs[u["cross_source"]] = xs.get(u["cross_source"], 0) + 1
            xs_tot[u["cross_source"]] += 1
        print(f"  {a['id']}: units={len(a['units'])} status={st} cross_source={xs}")
    print(f"cross_source_totals={xs_tot}")
    typos = data["summary"]["source_a_suspect_typos"]
    print(f"source_a_suspect_typos ({len(typos)}):")
    for t in typos:
        print(f"  {t['ayah_id']}: {t['a_word']} → {t['b_word']} (unit {t['unit_id']})")
    print(f"html_bytes={html_path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
