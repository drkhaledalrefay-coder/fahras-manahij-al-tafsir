"""Run phase-1 + phase-1b pipeline; print summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fetch  # noqa: E402
import layers  # noqa: E402
import pilot_windows  # noqa: E402
import reconcile  # noqa: E402
import reconcile_author  # noqa: E402
import spans  # noqa: E402
import spans_author  # noqa: E402


def _pinned_raw_ready() -> bool:
    """True when phase-1 raw extracts + manifest already exist (do not rewrite)."""
    manifest_path = ROOT / "data" / "raw" / "manifest.json"
    if not manifest_path.is_file():
        return False
    for surah, ayah in ((2, 255), (17, 105), (2, 102)):
        key = f"{surah}_{ayah}"
        if not (ROOT / "data" / "raw" / "tafsircenter" / f"{key}.txt").is_file():
            return False
        if not (ROOT / "data" / "raw" / "quran_com" / f"{key}.txt").is_file():
            return False
    return True


def main() -> int:
    print("=== FETCH ===")
    if _pinned_raw_ready():
        manifest = json.loads(
            (ROOT / "data" / "raw" / "manifest.json").read_bytes().decode("utf-8")
        )
        print("Reusing pinned data/raw/ (manifest + extracts present; fetch skipped)")
    else:
        manifest = fetch.fetch_all()
    meta_a = manifest["source_a"]
    meta_b = manifest["source_b"]
    print(f"Source A: {meta_a.get('dataset')} license={meta_a.get('license')} table={meta_a.get('table')}")
    print(f"Source B: {meta_b.get('source')} used={meta_b.get('used')} resource={meta_b.get('resource') or meta_b.get('edition_id')}")

    print("\n=== RECONCILE ===")
    report = reconcile.reconcile()
    for r in report["ayahs"]:
        print(
            f"{r['ayah']}: chars A/B={r['length_a']}/{r['length_b']} "
            f"exact_L0={'yes' if r['exact_match_l0'] else 'no'} "
            f"exact_L1={'yes' if r['exact_match_l1'] else 'no'} "
            f"ratio_L1={r['similarity_ratio_l1']} "
            f"diff_regions={r['word_diff_l1_region_count']}"
        )
    print(f"Independence: {report['independence']['answer']}")

    print("\n=== SPANS (Source A) ===")
    span_summary = spans.build_spans()
    for key, n in span_summary.items():
        print(f"{key}: {n} spans")

    print("\n=== LAYERS (author vs editor) ===")
    layer_summary = layers.build_layers()

    print("\n=== RECONCILE AUTHOR ===")
    author_report = reconcile_author.reconcile_author()
    for r in author_report["ayahs"]:
        print(
            f"{r['ayah']}: before={r['similarity_ratio_l1_before']} "
            f"after={r['similarity_ratio_l1_after']} "
            f"exact_L1={'yes' if r['exact_match_l1_author'] else 'no'} "
            f"diffs={r['word_diff_l1_region_count']} "
            f"editor_brackets={r['editor_bracket_count']}"
        )

    print("\n=== SPANS AUTHOR ===")
    spans_author_summary = spans_author.build_spans_author()
    for key, n in spans_author_summary.items():
        print(f"{key}: {n} author spans")

    print("\n=== PILOT WINDOWS ===")
    pilot_summary = pilot_windows.build_pilot_windows()

    print("\n=== SUMMARY ===")
    print(
        json.dumps(
            {
                "source_a_license": meta_a.get("license"),
                "source_b": meta_b.get("source"),
                "ayahs": [
                    {
                        "ayah": r["ayah"],
                        "chars_a": r["length_a"],
                        "chars_b": r["length_b"],
                        "exact_l0": r["exact_match_l0"],
                        "exact_l1": r["exact_match_l1"],
                        "ratio_l1": r["similarity_ratio_l1"],
                        "spans": span_summary.get(r["ayah"].replace(":", "_")),
                        "layer_chars": layer_summary.get(r["ayah"].replace(":", "_")),
                        "ratio_l1_author_before": next(
                            a["similarity_ratio_l1_before"]
                            for a in author_report["ayahs"]
                            if a["ayah"] == r["ayah"]
                        ),
                        "ratio_l1_author_after": next(
                            a["similarity_ratio_l1_after"]
                            for a in author_report["ayahs"]
                            if a["ayah"] == r["ayah"]
                        ),
                        "spans_author": spans_author_summary.get(r["ayah"].replace(":", "_")),
                        "pilot_spans": pilot_summary.get(r["ayah"].replace(":", "_"), {}).get(
                            "span_count"
                        ),
                    }
                    for r in report["ayahs"]
                ],
                "independence": report["independence"]["answer"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
