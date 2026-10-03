"""Reconcile author-layer Source A vs Source B at L1; list editor_bracket ranges."""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from layers import author_text_from_ranges, classify  # noqa: E402
from textcore import read_exact as _read_exact

from normalize import l1_normalize  # noqa: E402
from reconcile import _resolve_source_dirs, _word_diff  # noqa: E402

RAW = ROOT / "data" / "raw"
LAYERS_DIR = ROOT / "data" / "layers"
REPORTS = ROOT / "reports"
TARGET_AYAT = [(2, 255), (17, 105), (2, 102)]




def _load_or_classify(key: str, text_a: str) -> list[dict]:
    path = LAYERS_DIR / f"{key}.json"
    if path.is_file():
        payload = json.loads(path.read_bytes().decode("utf-8"))
        return payload["ranges"]
    return classify(text_a)


def _before_ratios_from_phase1() -> dict[str, float]:
    """Reuse full-A-vs-B L1 ratios from phase-1 reconciliation when present."""
    path = REPORTS / "reconciliation.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_bytes().decode("utf-8"))
    out: dict[str, float] = {}
    for r in data.get("ayahs", []):
        out[r["ayah"]] = float(r["similarity_ratio_l1"])
    return out


def reconcile_author() -> dict:
    manifest_path = RAW / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("data/raw/manifest.json missing; run fetch first")
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    dir_a, dir_b, meta_a, meta_b = _resolve_source_dirs(manifest)
    before_ratios = _before_ratios_from_phase1()

    ayah_reports = []
    for surah, ayah in TARGET_AYAT:
        key = f"{surah}_{ayah}"
        ayah_key = f"{surah}:{ayah}"
        path_a = dir_a / f"{key}.txt"
        path_b = dir_b / f"{key}.txt"
        text_a = _read_exact(path_a)
        text_b = _read_exact(path_b)
        ranges = _load_or_classify(key, text_a)
        author_text = author_text_from_ranges(text_a, ranges)

        a1_author = l1_normalize(author_text)
        b1 = l1_normalize(text_b)

        if ayah_key in before_ratios:
            ratio_before = before_ratios[ayah_key]
        else:
            a1_full = l1_normalize(text_a)
            ratio_before = difflib.SequenceMatcher(None, a1_full, b1, autojunk=False).ratio()
        ratio_after = difflib.SequenceMatcher(None, a1_author, b1, autojunk=False).ratio()
        exact_l1 = a1_author == b1
        regions = _word_diff(a1_author, b1, max_regions=20)

        editor_brackets = []
        for r in ranges:
            if r["layer"] == "editor_bracket":
                editor_brackets.append(
                    {
                        "start": r["start"],
                        "end": r["end"],
                        "text": text_a[r["start"] : r["end"]],
                    }
                )

        ayah_reports.append(
            {
                "ayah": f"{surah}:{ayah}",
                "surah": surah,
                "ayah_number": ayah,
                "length_a_full": len(text_a),
                "length_a_author": len(author_text),
                "length_b": len(text_b),
                "similarity_ratio_l1_before": round(ratio_before, 6),
                "similarity_ratio_l1_after": round(ratio_after, 6),
                "exact_match_l1_author": exact_l1,
                "word_diff_l1_regions": regions,
                "word_diff_l1_region_count": len(regions),
                "editor_bracket_count": len(editor_brackets),
                "editor_brackets": editor_brackets,
            }
        )

    report = {
        "ayahs": ayah_reports,
        "source_a": meta_a,
        "source_b": meta_b,
        "notes": (
            "Author-layer reconciliation strips footnote (¬…¥), verse_ref, and "
            "editor_bracket ranges from Source A before L1 comparison with Source B."
        ),
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "reconciliation_author.json").write_bytes(
        json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    )

    md_lines = [
        "# Author-Layer Reconciliation Report",
        "",
        "## Sources",
        "",
        f"- **Source A**: `{meta_a.get('dataset')}` (author ranges only after layer strip)",
        f"- **Source B**: `{meta_b.get('source')}` (used=`{meta_b.get('used')}`)",
        "",
        report["notes"],
        "",
        "## Per-ayah",
        "",
    ]
    for r in ayah_reports:
        md_lines.extend(
            [
                f"### {r['ayah']}",
                "",
                f"- Length A full / author / B: {r['length_a_full']} / {r['length_a_author']} / {r['length_b']}",
                f"- Similarity ratio L1 before (full A vs B): {r['similarity_ratio_l1_before']}",
                f"- Similarity ratio L1 after (author vs B): {r['similarity_ratio_l1_after']}",
                f"- Exact match L1 (author vs B): {'yes' if r['exact_match_l1_author'] else 'no'}",
                f"- Remaining word-level diff regions (max 20): {r['word_diff_l1_region_count']}",
                f"- editor_bracket ranges: {r['editor_bracket_count']}",
                "",
            ]
        )
        if r["word_diff_l1_regions"]:
            md_lines.append("| # | op | a_pos | b_pos | A (author) | B |")
            md_lines.append("|---|----|-------|-------|------------|---|")
            for i, reg in enumerate(r["word_diff_l1_regions"], 1):
                a_t = reg["a_text"].replace("|", "\\|")
                b_t = reg["b_text"].replace("|", "\\|")
                if len(a_t) > 120:
                    a_t = a_t[:117] + "..."
                if len(b_t) > 120:
                    b_t = b_t[:117] + "..."
                md_lines.append(
                    f"| {i} | {reg['op']} | {reg['a_word_pos']} | {reg['b_word_pos']} | {a_t} | {b_t} |"
                )
            md_lines.append("")
        else:
            md_lines.append("_No differing regions at L1 (author vs B)._")
            md_lines.append("")

        md_lines.append("#### editor_bracket texts")
        md_lines.append("")
        if not r["editor_brackets"]:
            md_lines.append("_None._")
            md_lines.append("")
        else:
            for i, eb in enumerate(r["editor_brackets"], 1):
                md_lines.append(f"{i}. `[{eb['start']}:{eb['end']}]` {eb['text']}")
            md_lines.append("")

    (REPORTS / "reconciliation_author.md").write_bytes("\n".join(md_lines).encode("utf-8"))
    return report


if __name__ == "__main__":
    rep = reconcile_author()
    for r in rep["ayahs"]:
        print(
            f"{r['ayah']}: before={r['similarity_ratio_l1_before']} "
            f"after={r['similarity_ratio_l1_after']} "
            f"exact_L1={'yes' if r['exact_match_l1_author'] else 'no'} "
            f"diffs={r['word_diff_l1_region_count']} "
            f"editor_brackets={r['editor_bracket_count']}"
        )
