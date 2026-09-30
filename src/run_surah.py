"""Reproducible pipeline for surah extraction, windowing, and classification.

Extracts verse texts from a read-only SQLite quran.db, partitions into author spans,
builds analysis windows (with paragraph packing for long verses), detects methodology
markers, and builds classifier packets. Idempotent: skips existing valid windows.
Optionally loops classifier with per-window time cap and stops on HTTP 429.

Examples:
  python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_tabari --surah 8 --base data/anfal/al_tabari --dry-run
  python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_tabari --surah 8 --ayat 1-20 --base data/anfal/al_tabari
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import multi_layers  # noqa: E402
import spans_author  # noqa: E402
import v2_markers  # noqa: E402
import v2_packets  # noqa: E402

EXPECTED_DB_SHA256 = "10e61f615ab5e6a3440e8ecc8ba1dc2273d12cd9048752760fe53a44d191cc27"

TAFSIR_INFO = {
    "al_tabari": {
        "table": "tafsir_tabary",
        "name_ar": "الطبري",
    },
    "al_saadi": {
        "table": "tafsir_saadi",
        "name_ar": "السعدي",
    },
    "al_baghawi": {
        "table": "tafsir_baghawy",
        "name_ar": "البغوي",
    },
    "ibn_kathir": {
        "table": "tafsir_katheer",
        "name_ar": "ابن كثير",
    },
}

# Pre-defined split points for multi-part verses if needed
CUSTOM_SPLITS = {
    "ibn_kathir": {
        "8_1": [14, 113],
        "8_41": [85],
    }
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _format_path(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def parse_ayat(ayat_spec: str | None) -> list[int] | None:
    if not ayat_spec:
        return None
    spec = ayat_spec.strip()
    if "-" in spec:
        parts = spec.split("-", 1)
        start = int(parts[0].strip())
        end = int(parts[1].strip())
        return list(range(start, end + 1))
    if "," in spec:
        return [int(x.strip()) for x in spec.split(",") if x.strip()]
    return [int(spec)]


def get_all_ayat_for_surah(conn: sqlite3.Connection, table: str, surah: int) -> list[int]:
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT [aya] FROM [{table}] WHERE [sura]=? ORDER BY [aya]", (surah,))
    rows = cur.fetchall()
    return [r[0] for r in rows]


def validate_existing_window(base: Path, win_id: str) -> bool:
    win_file = base / "windows" / f"{win_id}.json"
    marker_file = base / "markers" / f"{win_id}.json"
    pkt_file = base / "packets" / f"{win_id}.json"
    if not win_file.is_file() or not marker_file.is_file() or not pkt_file.is_file():
        return False
    try:
        w = json.loads(win_file.read_bytes().decode("utf-8"))
        m = json.loads(marker_file.read_bytes().decode("utf-8"))
        p = json.loads(pkt_file.read_bytes().decode("utf-8"))
        if w.get("window_id") != win_id or not w.get("spans"):
            return False
        if len(w["spans"]) != w.get("span_count"):
            return False
        w_text = w.get("window_text") or ""
        for s in w["spans"]:
            if w_text[s["start"] - w["window_start"] : s["end"] - w["window_start"]] != s["text"]:
                return False
        if not m.get("spans") or "family_counts" not in m:
            return False
        if not p.get("spans") or not p.get("definitions"):
            return False
        return True
    except Exception:
        return False


def get_para_breaks(raw_text: str, spans: list[dict]) -> set[int]:
    breaks = set()
    for i in range(len(spans) - 1):
        s1 = spans[i]
        s2 = spans[i + 1]
        inter = raw_text[s1["end"] : s2["start"]]
        if (
            "<br>" in inter
            or "<br/>" in inter
            or "<br />" in inter
            or "\n" in inter
            or s1["text"].endswith("\n")
            or s1["text"].endswith("\r\n")
        ):
            breaks.add(i)
    return breaks


def partition_spans(
    spans: list[dict],
    raw_text: str,
    tafsir_id: str,
    key: str,
    cap: int = 110,
) -> list[tuple[int, int]]:
    n = len(spans)
    if n <= cap:
        return [(0, n - 1)]

    # Check for custom splits
    if tafsir_id in CUSTOM_SPLITS and key in CUSTOM_SPLITS[tafsir_id]:
        cut_indices = CUSTOM_SPLITS[tafsir_id][key]
        parts = []
        start = 0
        for cut in cut_indices:
            parts.append((start, cut))
            start = cut + 1
        parts.append((start, n - 1))
        return parts

    # Greedy paragraph packing up to cap
    pbreaks = get_para_breaks(raw_text, spans)
    parts = []
    start = 0
    while start < n:
        if n - start <= cap:
            parts.append((start, n - 1))
            break
        limit = start + cap - 1
        candidates = [b for b in pbreaks if start <= b <= limit]
        cut = max(candidates) if candidates else limit
        parts.append((start, cut))
        start = cut + 1
    return parts


def _find_window_files(base: Path, key: str) -> list[Path]:
    single = base / "windows" / f"{key}.json"
    if single.is_file():
        return [single]
    return sorted(base.glob(f"windows/{key}_p*.json"))


def process_ayah(
    conn: sqlite3.Connection,
    tafsir_id: str,
    table: str,
    tafsir_name: str,
    surah: int,
    ayah: int,
    base: Path,
) -> list[str]:
    """Process a single ayah: raw -> layers -> spans -> windows -> markers -> packets."""
    key = f"{surah}_{ayah}"

    # Check if windows already exist and are valid
    existing_win_files = _find_window_files(base, key)
    if existing_win_files:
        all_valid = all(validate_existing_window(base, wf.stem) for wf in existing_win_files)
        if all_valid:
            print(f"skip {key} ({len(existing_win_files)} window(s) exist and valid)")
            return [wf.stem for wf in existing_win_files]

    cur = conn.cursor()
    cur.execute(f"SELECT [tafsir] FROM [{table}] WHERE [sura]=? AND [aya]=?", (surah, ayah))
    row = cur.fetchone()
    if not row or row[0] is None:
        raise SystemExit(f"Missing DB row for {tafsir_id} {surah}:{ayah}")
    raw_text = str(row[0])
    raw_bytes = raw_text.encode("utf-8")
    raw_sha = _sha256_bytes(raw_bytes)

    # 1. raw
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{key}.txt"
    raw_file.write_bytes(raw_bytes)

    # Canonical source file path relative to ROOT (or standard data/anfal/<id>)
    try:
        rel_source = str(raw_file.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        rel_source = f"data/anfal/{tafsir_id}/raw/{key}.txt"

    # 2. layers
    ranges = multi_layers.classify(raw_text)
    survey = multi_layers.survey_patterns(raw_text)
    stats = multi_layers.range_stats(ranges, raw_text)
    layers_payload = {
        "source": "tafsircenter",
        "tafsir_id": tafsir_id,
        "source_file": rel_source,
        "ayah": f"{surah}:{ayah}",
        "surah": surah,
        "ayah_number": ayah,
        "source_char_length": len(raw_text),
        "ranges": ranges,
        "range_counts": stats["range_counts"],
        "char_totals": stats["char_totals"],
        "apparatus_subtype_counts": stats["apparatus_subtype_counts"],
        "apparatus_subtype_chars": stats["apparatus_subtype_chars"],
        "survey": survey,
    }
    layers_dir = base / "layers"
    layers_dir.mkdir(parents=True, exist_ok=True)
    layers_file = layers_dir / f"{key}.json"
    layers_file.write_bytes(
        json.dumps(layers_payload, ensure_ascii=False, indent=2).encode("utf-8")
    )

    # 3. spans
    author_ranges = [(r["start"], r["end"]) for r in ranges if r["kind"] == "author"]
    author_text = multi_layers.author_text_from_ranges(raw_text, ranges)
    spans: list[dict] = []
    for ar_start, ar_end in author_ranges:
        chunk = raw_text[ar_start:ar_end]
        for loc_a, loc_b in spans_author.segment_author_chunk(chunk):
            start = ar_start + loc_a
            end = ar_start + loc_b
            spans.append({"start": start, "end": end, "text": raw_text[start:end]})
    for i, s in enumerate(spans, 1):
        s["id"] = f"s{i:03d}"

    spans_payload = {
        "source": "tafsircenter",
        "tafsir_id": tafsir_id,
        "source_file": rel_source,
        "ayah": f"{surah}:{ayah}",
        "surah": surah,
        "ayah_number": ayah,
        "source_sha256": raw_sha,
        "source_char_length": len(raw_text),
        "author_char_length": len(author_text),
        "span_count": len(spans),
        "spans": spans,
    }
    spans_dir = base / "spans"
    spans_dir.mkdir(parents=True, exist_ok=True)
    spans_file = spans_dir / f"{key}.json"
    spans_file.write_bytes(
        json.dumps(spans_payload, ensure_ascii=False, indent=2).encode("utf-8")
    )

    # 4. windows + markers + packets
    windows_dir = base / "windows"
    markers_dir = base / "markers"
    packets_dir = base / "packets"
    windows_dir.mkdir(parents=True, exist_ok=True)
    markers_dir.mkdir(parents=True, exist_ok=True)
    packets_dir.mkdir(parents=True, exist_ok=True)

    parts = partition_spans(spans, raw_text, tafsir_id, key, cap=110)
    generated_window_ids = []

    for p_idx, (p_start, p_end) in enumerate(parts, 1):
        if len(parts) == 1:
            w_id = key
            rule = "all_spans"
            part_num = None
            part_count = None
            capped_110 = False
        else:
            w_id = f"{key}_p{p_idx:02d}"
            rule = "paragraph_pack_cap_110"
            part_num = p_idx
            part_count = len(parts)
            capped_110 = (p_end - p_start + 1) == 110

        part_spans = spans[p_start : p_end + 1]
        win_start = part_spans[0]["start"]
        win_end = part_spans[-1]["end"]

        apparatus = []
        for r in ranges:
            if r.get("kind") == "apparatus" and not (
                r["end"] <= win_start or r["start"] >= win_end
            ):
                apparatus.append(
                    {
                        "start": r["start"],
                        "end": r["end"],
                        "kind": "apparatus",
                        "subtype": r.get("subtype"),
                        "text": raw_text[r["start"] : r["end"]],
                    }
                )

        win_payload = {
            "window_id": w_id,
            "tafsir_id": tafsir_id,
            "ayah": f"{surah}:{ayah}",
            "surah": surah,
            "ayah_number": ayah,
            "source": "tafsircenter",
            "source_file": rel_source,
            "source_sha256": raw_sha,
            "window_start": win_start,
            "window_end": win_end,
            "window_text": raw_text[win_start:win_end],
            "span_count": len(part_spans),
            "spans": [
                {"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"]}
                for s in part_spans
            ],
            "apparatus": apparatus,
            "selection": {
                "rule": rule,
                "start_span_id": part_spans[0]["id"],
                "end_span_id": part_spans[-1]["id"],
                "start_index": p_start,
                "end_index": p_end,
                "char_length": win_end - win_start,
                "part": part_num,
                "part_count": part_count,
                "capped_at_110": capped_110,
            },
        }
        win_file = windows_dir / f"{w_id}.json"
        win_file.write_bytes(
            json.dumps(win_payload, ensure_ascii=False, indent=2).encode("utf-8")
        )

        marker_payload = v2_markers.build_markers_for_window(win_payload, tafsir_name=tafsir_name)
        marker_file = markers_dir / f"{w_id}.json"
        marker_file.write_bytes(
            json.dumps(marker_payload, ensure_ascii=False, indent=2).encode("utf-8")
        )

        pkt_payload = v2_packets.build_packet(win_payload, marker_payload, tafsir_name=tafsir_name)
        pkt_file = packets_dir / f"{w_id}.json"
        pkt_file.write_bytes(
            json.dumps(pkt_payload, ensure_ascii=False, indent=2).encode("utf-8")
        )

        generated_window_ids.append(w_id)
        print(f"wrote {w_id} spans={len(part_spans)} chars={win_end - win_start}")

    return generated_window_ids


def run_classification_loop(
    base: Path,
    window_ids: list[str],
    dry_run: bool = False,
    time_cap: int = 120,
) -> None:
    """Loop run_window.py over windows with per-window time cap; stop on HTTP 429."""
    run_window_script = ROOT / "src" / "run_window.py"
    for win_id in window_ids:
        cmd = [
            sys.executable,
            str(run_window_script),
            "--base",
            str(base),
            "--window",
            win_id,
        ]
        if dry_run:
            cmd.append("--dry-run")
        else:
            cmd.append("--api")

        print(f"--> classifying window {win_id} (timeout={time_cap}s)...")
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=time_cap,
            )
        except subprocess.TimeoutExpired:
            print(f"Time cap of {time_cap}s exceeded on window {win_id}. Stopping.")
            break

        out_combined = (res.stdout or "") + (res.stderr or "")
        if "429" in out_combined or "rate limit" in out_combined.lower():
            print(f"HTTP 429 rate limit exceeded on window {win_id}:\n{out_combined.strip()}")
            print("Stopping classification chain on first HTTP 429.")
            break

        if res.returncode != 0:
            print(f"Error on window {win_id} (exit code {res.returncode}):\n{out_combined.strip()}")
            break

        if res.stdout:
            print(res.stdout.strip())


def run_surah(
    db_path: Path,
    tafsir: str,
    surah: int = 8,
    ayat: list[int] | None = None,
    base: Path | str | None = None,
    dry_run: bool = False,
    classify: bool = False,
    time_cap: int = 120,
) -> list[str]:
    if tafsir not in TAFSIR_INFO:
        raise SystemExit(
            f"unknown tafsir {tafsir!r}; choose: {', '.join(sorted(TAFSIR_INFO.keys()))}"
        )

    tinfo = TAFSIR_INFO[tafsir]
    table = tinfo["table"]
    name_ar = tinfo["name_ar"]

    if base is None:
        base_dir = ROOT / "data" / "anfal" / tafsir
    else:
        base_dir = Path(base)
        if not base_dir.is_absolute():
            base_dir = (ROOT / base_dir).resolve()
        else:
            base_dir = base_dir.resolve()

    if not db_path.is_file():
        raise SystemExit(f"DB not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        target_ayat = ayat or get_all_ayat_for_surah(conn, table, surah)
        if not target_ayat:
            raise SystemExit(f"No verses found for surah {surah} in {table}")

        print(
            f"run_surah: tafsir={tafsir} surah={surah} ayat={len(target_ayat)} "
            f"base={_format_path(base_dir)}"
        )

        all_window_ids = []
        if dry_run and not classify:
            # Check what exists or would be extracted
            for ayah in target_ayat:
                key = f"{surah}_{ayah}"
                existing = _find_window_files(base_dir, key)
                if existing:
                    all_window_ids.extend([f.stem for f in existing])
                else:
                    all_window_ids.append(key)
            print(f"dry-run: {len(target_ayat)} verses checked; no network call")
            return all_window_ids

        for ayah in target_ayat:
            w_ids = process_ayah(conn, tafsir, table, name_ar, surah, ayah, base_dir)
            all_window_ids.extend(w_ids)

        if classify:
            run_classification_loop(
                base_dir, all_window_ids, dry_run=dry_run, time_cap=time_cap
            )

        return all_window_ids
    finally:
        conn.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reproduce tafsir extraction chain for a surah."
    )
    p.add_argument("--db", required=True, type=Path, help="Path to quran.db (opened read-only)")
    p.add_argument(
        "--tafsir",
        required=True,
        choices=list(TAFSIR_INFO.keys()),
        help="al_tabari | al_saadi | al_baghawi | ibn_kathir",
    )
    p.add_argument("--surah", type=int, default=8, help="Surah number (default: 8)")
    p.add_argument("--ayat", default=None, help="Ayat range e.g. 1-20, or 2,3,4")
    p.add_argument("--base", default=None, help="Base output dir (e.g. data/anfal/al_tabari)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate run or pass dry-run to classifier; never call model",
    )
    p.add_argument(
        "--classify",
        action="store_true",
        help="Loop run_window.py over windows with per-window time cap",
    )
    p.add_argument(
        "--time-cap",
        type=int,
        default=120,
        help="Per-window time cap in seconds for classification (default: 120)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ayat = parse_ayat(args.ayat)
    base = Path(args.base) if args.base else None
    run_surah(
        db_path=args.db.resolve(),
        tafsir=args.tafsir,
        surah=args.surah,
        ayat=ayat,
        base=base,
        dry_run=args.dry_run,
        classify=args.classify,
        time_cap=args.time_cap,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
