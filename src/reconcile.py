"""Reconcile Source A vs Source B tafsir texts at L0 and L1."""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from normalize import l0_raw, l1_normalize  # noqa: E402

RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "reports"
TARGET_AYAT = [(2, 255), (17, 105), (2, 102)]


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _word_diff(a: str, b: str, max_regions: int = 30) -> list[dict]:
    a_words = a.split()
    b_words = b.split()
    sm = difflib.SequenceMatcher(None, a_words, b_words, autojunk=False)
    regions: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        regions.append(
            {
                "op": tag,
                "a_word_pos": i1,
                "b_word_pos": j1,
                "a_text": " ".join(a_words[i1:i2]),
                "b_text": " ".join(b_words[j1:j2]),
            }
        )
        if len(regions) >= max_regions:
            break
    return regions


def _resolve_source_dirs(manifest: dict) -> tuple[Path, Path, dict, dict]:
    meta_a = manifest["source_a"]
    meta_b = manifest["source_b"]
    dir_a = ROOT / "data" / "raw" / "tafsircenter"
    if meta_b.get("source") == "quran_com":
        dir_b = ROOT / "data" / "raw" / "quran_com"
    else:
        dir_b = ROOT / "data" / "raw" / "jsdelivr_tafsir_api"
    return dir_a, dir_b, meta_a, meta_b


def reconcile() -> dict:
    manifest_path = RAW / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("data/raw/manifest.json missing; run fetch first")
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    dir_a, dir_b, meta_a, meta_b = _resolve_source_dirs(manifest)

    ayah_reports = []
    for surah, ayah in TARGET_AYAT:
        key = f"{surah}_{ayah}"
        path_a = dir_a / f"{key}.txt"
        path_b = dir_b / f"{key}.txt"
        text_a = _read_exact(path_a)
        text_b = _read_exact(path_b)
        a0, b0 = l0_raw(text_a), l0_raw(text_b)
        a1, b1 = l1_normalize(text_a), l1_normalize(text_b)
        exact_l0 = a0 == b0
        exact_l1 = a1 == b1
        ratio = difflib.SequenceMatcher(None, a1, b1, autojunk=False).ratio()
        regions = _word_diff(a1, b1, max_regions=30)
        ayah_reports.append(
            {
                "ayah": f"{surah}:{ayah}",
                "surah": surah,
                "ayah_number": ayah,
                "length_a": len(text_a),
                "length_b": len(text_b),
                "length_a_l1": len(a1),
                "length_b_l1": len(b1),
                "exact_match_l0": exact_l0,
                "exact_match_l1": exact_l1,
                "similarity_ratio_l1": round(ratio, 6),
                "word_diff_l1_regions": regions,
                "word_diff_l1_region_count": len(regions),
            }
        )

    independence = {
        "question": "Do A and B appear to share an upstream edition?",
        "answer": "unknown",
        "source_a_metadata": {
            "license": meta_a.get("license"),
            "dataset": meta_a.get("dataset"),
            "table": meta_a.get("table"),
            "edition_publisher_metadata": meta_a.get("edition_publisher_metadata"),
        },
        "source_b_metadata": {
            "source": meta_b.get("source"),
            "used": meta_b.get("used"),
            "resource": meta_b.get("resource") or {
                "edition_id": meta_b.get("edition_id"),
            },
            "by_ayah_resource_fields": meta_b.get("by_ayah_resource_fields"),
        },
        "notes": (
            "Source A attributes content to Tafsir Center for Quranic Studies "
            "(tafsir.net) / HF dataset tafsircenter/tafsir-mcp-data; no print-edition "
            "id in DB. Source B (quran.com) exposes resource name/author/language/slug "
            "but no shared edition identifier linking it to Source A. "
            "Shared upstream edition cannot be verified from available metadata."
        ),
    }

    report = {
        "ayahs": ayah_reports,
        "independence": independence,
        "source_a": meta_a,
        "source_b": meta_b,
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / "reconciliation.json"
    json_path.write_bytes(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))

    md_lines = [
        "# Reconciliation Report",
        "",
        "## Sources",
        "",
        f"- **Source A**: `{meta_a.get('dataset')}` — license `{meta_a.get('license')}`; "
        f"table `{meta_a.get('table')}` columns `{meta_a.get('columns')}`",
        f"- **Source B**: `{meta_b.get('source')}` (used=`{meta_b.get('used')}`) — "
        f"`{meta_b.get('resource') or meta_b.get('edition_id')}`",
        "",
        "## Per-ayah",
        "",
    ]
    for r in ayah_reports:
        md_lines.extend(
            [
                f"### {r['ayah']}",
                "",
                f"- Length A/B (L0 chars): {r['length_a']} / {r['length_b']}",
                f"- Exact match L0: {'yes' if r['exact_match_l0'] else 'no'}",
                f"- Exact match L1: {'yes' if r['exact_match_l1'] else 'no'}",
                f"- Similarity ratio L1: {r['similarity_ratio_l1']}",
                f"- Word-level diff regions (L1, max 30): {r['word_diff_l1_region_count']}",
                "",
            ]
        )
        if r["word_diff_l1_regions"]:
            md_lines.append("| # | op | a_pos | b_pos | A | B |")
            md_lines.append("|---|----|-------|-------|---|---|")
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
            md_lines.append("_No differing regions at L1._")
            md_lines.append("")

    md_lines.extend(
        [
            "## Independence",
            "",
            f"**Do A and B appear to share an upstream edition?** {independence['answer']}",
            "",
            independence["notes"],
            "",
            "### Metadata cited",
            "",
            "```json",
            json.dumps(
                {
                    "source_a": independence["source_a_metadata"],
                    "source_b": independence["source_b_metadata"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
        ]
    )
    (REPORTS / "reconciliation.md").write_bytes("\n".join(md_lines).encode("utf-8"))
    return report


if __name__ == "__main__":
    rep = reconcile()
    for r in rep["ayahs"]:
        print(
            f"{r['ayah']}: L0={'yes' if r['exact_match_l0'] else 'no'} "
            f"L1={'yes' if r['exact_match_l1'] else 'no'} "
            f"ratio={r['similarity_ratio_l1']} "
            f"diffs={r['word_diff_l1_region_count']}"
        )
    print("Independence:", rep["independence"]["answer"])
