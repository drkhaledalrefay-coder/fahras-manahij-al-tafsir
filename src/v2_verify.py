"""Verify classifier moves: IDs, rules, auditable score, specialist routing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

DEFAULT_BASE = "data/v2"
DEFAULT_V2_BASE = (ROOT / "data" / "v2").resolve()

WINDOWS_DIR = ROOT / "data" / "v2" / "windows"
MARKERS_DIR = ROOT / "data" / "v2" / "markers"
MOVES_DIR = ROOT / "data" / "v2" / "moves"
VERIFIED_DIR = ROOT / "data" / "v2" / "verified"
REPORTS_DIR = ROOT / "reports"
SUMMARY_PATH = ROOT / "reports" / "v2_summary.md"
MOVES_HINT = "data/v2/moves/<annotator>/<window>.json"
VERIFY_CMD_HINT = "python src/v2_verify.py"

PRIMARY_METHODS = {
    "M_QURAN",
    "M_SUNNAH",
    "M_SAHABA",
    "M_TABIIN",
    "M_LUGHA",
    "M_QIRAAT",
    "M_NUZUL",
    "M_SIRA",
    "M_ISRAILIYYAT",
    "M_RAY",
    None,
}

CERTAINTY_RANK = {
    "explicit": 3,
    "strong": 2,
    "weak": 1,
    "insufficient": 0,
}

FORCE_SPECIALIST_METHODS = {"M_ISRAILIYYAT", "M_NUZUL", "M_QIRAAT"}

FAMILY_FOR_PRIMARY = {
    "M_QURAN": "QURAN",
    "M_SUNNAH": "HADITH",
    "M_SAHABA": "SAHABA",
    "M_TABIIN": "TABIIN",
    "M_LUGHA": "LUGHA",
    "M_QIRAAT": "QIRAAT",
    "M_NUZUL": "NUZUL",
    "M_SIRA": "SIRA",
    "M_ISRAILIYYAT": "ISRAILIYYAT",
    "M_RAY": "RAY",
}

# Soft flags: routing/measurement notes that must not further crush certainty.
SOFT_RULE_FLAGS = frozenset(
    {
        "rule_explicit_without_marker",
        "rule_ray_unmeasured",
    }
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _resolve_base(base: str | Path) -> Path:
    p = Path(base)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def configure(base: str | Path = DEFAULT_BASE) -> Path:
    """Point windows/markers/moves/verified at <base>; set summary path."""
    global WINDOWS_DIR, MARKERS_DIR, MOVES_DIR, VERIFIED_DIR, SUMMARY_PATH
    global MOVES_HINT, VERIFY_CMD_HINT
    base_path = _resolve_base(base)
    WINDOWS_DIR = base_path / "windows"
    MARKERS_DIR = base_path / "markers"
    MOVES_DIR = base_path / "moves"
    VERIFIED_DIR = base_path / "verified"
    try:
        rel = base_path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = base_path.as_posix()
    if base_path == DEFAULT_V2_BASE:
        SUMMARY_PATH = ROOT / "reports" / "v2_summary.md"
        MOVES_HINT = "data/v2/moves/<annotator>/<window>.json"
        VERIFY_CMD_HINT = "python src/v2_verify.py"
    else:
        SUMMARY_PATH = base_path / "summary.md"
        MOVES_HINT = f"{rel}/moves/<annotator>/<window>.json"
        VERIFY_CMD_HINT = f"python src/v2_verify.py --base {rel}"
    return base_path


def _span_index(window: dict) -> dict[str, dict]:
    return {s["id"]: s for s in window["spans"]}


def _markers_for_spans(markers: dict, span_ids: list[str]) -> list[dict]:
    wanted = set(span_ids)
    out: list[dict] = []
    for block in markers.get("spans") or []:
        if block["span_id"] in wanted:
            out.extend(block.get("markers") or [])
    return out


def _has_family(hits: list[dict], family: str) -> bool:
    return any(h["family"] == family for h in hits)


def _has_speaker(hits: list[dict], family: str) -> bool:
    return any(h["family"] == family and h.get("role") == "SPEAKER" for h in hits)


def _isnad_ranges(markers: dict) -> list[tuple[int, int]]:
    return [(r["start"], r["end"]) for r in markers.get("isnad_ranges") or []]


def _point_in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in ranges)


def _name_only_in_isnad(hits: list[dict], family: str, isnad: list[tuple[int, int]]) -> bool:
    name_hits = [h for h in hits if h["family"] == family]
    if not name_hits:
        return False
    return all(h.get("role") == "NARRATOR" and _point_in_ranges(h["start"], isnad) for h in name_hits)


def _quran_only_inside_hadith(hits: list[dict]) -> bool:
    """True if QURAN quote markers exist but all sit inside a HADITH-bearing span set
    without an independent QURAN phrase marker (كما قال تعالى etc.)."""
    quran_quotes = [h for h in hits if h["family"] == "QURAN" and h["marker"] in ("{…}", "﴿…﴾")]
    quran_phrases = [
        h
        for h in hits
        if h["family"] == "QURAN" and h["marker"] not in ("{…}", "﴿…﴾", "verse_ref")
    ]
    hadith = [h for h in hits if h["family"] == "HADITH"]
    if not quran_quotes or not hadith or quran_phrases:
        return False
    # If every quote start falls within some hadith hit's span_id group — approximate:
    # quote is "inside hadith quotation" when a HADITH marker appears in evidence and
    # no interpretive QURAN phrase is present.
    return True


def validate_move_structure(
    move: dict, by_id: dict[str, dict]
) -> tuple[list[str], str]:
    """Return (flags, rebuilt_text)."""
    flags: list[str] = []
    span_ids = move.get("span_ids") or []
    if not span_ids:
        flags.append("empty_span_ids")
        return flags, ""

    missing = [sid for sid in span_ids if sid not in by_id]
    if missing:
        flags.append(f"unknown_span_ids:{','.join(missing)}")
        return flags, ""

    spans = [by_id[sid] for sid in span_ids]
    # Contiguity in author-span list order (by numeric id)
    nums = [int(sid[1:]) for sid in span_ids]
    if nums != list(range(nums[0], nums[0] + len(nums))):
        flags.append("non_contiguous_span_ids")

    rebuilt = "".join(s["text"] for s in spans)
    # Verbatim: each span text must equal source slice (already stored); re-check
    for s in spans:
        if not s["text"]:
            flags.append(f"empty_span_text:{s['id']}")

    primary = move.get("primary")
    if primary not in PRIMARY_METHODS and primary is not None:
        # allow JSON null already mapped; reject unknown strings
        if primary not in PRIMARY_METHODS:
            flags.append(f"unknown_primary:{primary}")

    certainty = move.get("certainty")
    if certainty not in CERTAINTY_RANK:
        flags.append(f"unknown_certainty:{certainty}")

    evid = move.get("evidence_span_ids") or []
    for sid in evid:
        if sid not in by_id:
            flags.append(f"unknown_evidence_span:{sid}")

    return flags, rebuilt


def _allowed_evidence_ids(
    span_ids: list[str], ordered_ids: list[str]
) -> set[str]:
    """Move spans plus the single span immediately preceding the move."""
    allowed = set(span_ids)
    if span_ids and span_ids[0] in ordered_ids:
        idx = ordered_ids.index(span_ids[0])
        if idx:
            allowed.add(ordered_ids[idx - 1])
    return allowed


def _author_hits(hits: list[dict]) -> list[dict]:
    """Markers from author text only (exclude editor footnotes)."""
    return [h for h in hits if h.get("family") != "EDITOR"]


def _verdict_has_ray(markers: dict, verdict_ids: list[str]) -> bool:
    if not verdict_ids:
        return False
    return _has_family(_markers_for_spans(markers, verdict_ids), "RAY")


def _primary_marker_ok(
    move: dict, evidence_hits: list[dict], markers: dict
) -> bool:
    """True when the primary method has a real author-side family marker.

    Claimed author_verdict_span_ids earn credit only if those spans contain a
    RAY verdict marker. SAHABA/TABIIN require a SPEAKER role (including the
    preceding-span speaker already folded into evidence_hits).
    """
    primary = move.get("primary")
    author_hits = _author_hits(evidence_hits)
    if primary is None:
        return bool(author_hits)
    need = FAMILY_FOR_PRIMARY.get(primary)
    if not need:
        return False
    if primary in ("M_SAHABA", "M_TABIIN"):
        marker_ok = _has_speaker(author_hits, need)
    else:
        marker_ok = _has_family(author_hits, need)
    if primary in ("M_RAY", "M_ISRAILIYYAT"):
        marker_ok = marker_ok or _verdict_has_ray(
            markers, move.get("author_verdict_span_ids") or []
        )
    return marker_ok


def _refs_corroborated(refs: dict, evidence_hits: list[dict]) -> bool:
    """Claimed references count only when evidence markers back them."""
    author_hits = _author_hits(evidence_hits)
    if refs.get("verses") and _has_family(author_hits, "QURAN"):
        return True
    if refs.get("hadith") and _has_family(author_hits, "HADITH"):
        return True
    if refs.get("persons") and (
        _has_speaker(author_hits, "SAHABA") or _has_speaker(author_hits, "TABIIN")
    ):
        return True
    return False


def score_move(
    move: dict,
    flags: list[str],
    evidence_hits: list[dict],
    has_function_evidence: bool,
    has_attribution: bool,
    boundary_ok: bool,
    markers: dict,
) -> dict:
    """Auditable score: marker 25 + function 45 + attribution 15 + boundary 15.
    Cap 59 if no function evidence."""
    marker_ok = _primary_marker_ok(move, evidence_hits, markers)

    parts = {
        "marker": 25 if marker_ok else 0,
        "function_evidence": 45 if has_function_evidence else 0,
        "attribution": 15 if has_attribution else 0,
        "boundary": 15 if boundary_ok else 0,
    }
    total = sum(parts.values())
    if not has_function_evidence:
        total = min(total, 59)
    # Downgrade on rule flags
    if any(
        f.startswith("rule_") or f in ("non_contiguous_span_ids", "unknown_span_ids")
        for f in flags
    ):
        total = min(total, 59)
    return {"parts": parts, "total": total, "marker_ok": marker_ok}


def apply_rule_checks(
    move: dict, evidence_hits: list[dict], markers: dict, flags: list[str]
) -> list[str]:
    primary = move.get("primary")
    isnad = _isnad_ranges(markers)

    if primary == "M_QURAN":
        if not _has_family(evidence_hits, "QURAN"):
            flags.append("rule_M_QURAN_missing_marker")
        if _quran_only_inside_hadith(evidence_hits):
            flags.append("rule_M_QURAN_verse_inside_hadith")

    if primary == "M_SAHABA":
        if _name_only_in_isnad(evidence_hits, "SAHABA", isnad):
            flags.append("rule_M_SAHABA_name_only_in_isnad")
        if not _has_speaker(evidence_hits, "SAHABA"):
            flags.append("rule_M_SAHABA_missing_marker")

    if primary == "M_TABIIN":
        if _name_only_in_isnad(evidence_hits, "TABIIN", isnad):
            flags.append("rule_M_TABIIN_name_only_in_isnad")
        if not _has_speaker(evidence_hits, "TABIIN"):
            flags.append("rule_M_TABIIN_missing_marker")

    if primary == "M_ISRAILIYYAT":
        if not (
            _has_family(evidence_hits, "ISRAILIYYAT")
            or _verdict_has_ray(markers, move.get("author_verdict_span_ids") or [])
        ):
            flags.append("rule_M_ISRAILIYYAT_needs_marker_or_verdict")

    if primary == "M_NUZUL":
        if not _has_family(evidence_hits, "NUZUL"):
            flags.append("rule_M_NUZUL_missing_marker")

    if primary == "M_QIRAAT":
        if not _has_family(evidence_hits, "QIRAAT"):
            flags.append("rule_M_QIRAAT_missing_marker")

    if primary == "M_RAY":
        flags.append("rule_ray_unmeasured")

    # Editor footnotes never create a method by themselves — flag if primary set
    # with only EDITOR evidence and no author-side marker family.
    if primary and primary != "M_RAY":
        non_editor = [
            h for h in evidence_hits
            if h["family"] != "EDITOR"
            and not (h["family"] in ("SAHABA", "TABIIN") and h.get("role") == "NARRATOR")
        ]
        if not non_editor and evidence_hits:
            flags.append("rule_editor_only_evidence")

    return flags


def downgrade_certainty(certainty: str, flags: list[str]) -> str:
    if not flags:
        return certainty
    rule_flags = [
        f
        for f in flags
        if (f.startswith("rule_") or f.startswith("unknown_"))
        and f not in SOFT_RULE_FLAGS
    ]
    if not rule_flags:
        if "non_contiguous_span_ids" in flags:
            return "weak" if CERTAINTY_RANK.get(certainty, 0) > 1 else certainty
        return certainty
    rank = CERTAINTY_RANK.get(certainty, 0)
    if rank >= 2:
        return "weak"
    if rank == 1:
        return "insufficient"
    return certainty or "insufficient"


def assign_route(
    move: dict,
    certainty: str,
    score: int,
    flags: list[str],
    mixed_span: bool,
) -> str:
    primary = move.get("primary")
    if primary == "M_RAY":
        return "specialist"
    if certainty in ("weak", "insufficient"):
        return "specialist"
    if primary in FORCE_SPECIALIST_METHODS:
        return "specialist"
    if any(f.startswith("rule_M_SAHABA") or f.startswith("rule_M_TABIIN") for f in flags):
        return "specialist"
    if mixed_span:
        return "specialist"
    if flags:
        return "specialist"
    if certainty in ("explicit", "strong") and score >= 75:
        return "auto_candidate"
    return "specialist"


def verify_move(move: dict, window: dict, markers: dict) -> dict:
    by_id = _span_index(window)
    flags, rebuilt = validate_move_structure(move, by_id)

    ordered_ids = [s["id"] for s in window["spans"]]
    span_ids = [sid for sid in (move.get("span_ids") or []) if sid in by_id]
    allowed_evid = _allowed_evidence_ids(span_ids, ordered_ids)

    raw_evid = move.get("evidence_span_ids") or []
    if not raw_evid:
        # Empty claim → use move spans (always inside the move).
        evid_ids = span_ids
        has_function = bool(evid_ids) and "empty_span_ids" not in flags
    else:
        evid_claimed = [sid for sid in raw_evid if sid in by_id]
        outside = [sid for sid in evid_claimed if sid not in allowed_evid]
        if outside:
            flags.append("rule_evidence_outside_move")
        evid_ids = [sid for sid in evid_claimed if sid in allowed_evid]
        has_function = bool(evid_ids) and not outside and "empty_span_ids" not in flags

    evidence_hits = _markers_for_spans(markers, evid_ids)
    # Attribution may be in the author span immediately before the quotation.
    # Only speaker markers cross this boundary; unrelated method markers do not.
    attribution_family = {"M_SAHABA": "SAHABA", "M_TABIIN": "TABIIN"}.get(move.get("primary"))
    if evid_ids and attribution_family:
        first_index = ordered_ids.index(evid_ids[0])
        if first_index:
            previous = _markers_for_spans(markers, [ordered_ids[first_index - 1]])
            evidence_hits.extend(
                h for h in previous
                if h.get("role") == "SPEAKER" and h["family"] == attribution_family
            )
    # Attach editor footnotes linked to evidence spans
    for e in markers.get("editor_footnote_evidence") or []:
        if e.get("attached_span_id") in evid_ids or e.get("attached_span_id") in span_ids:
            evidence_hits.append(
                {
                    "family": "EDITOR",
                    "marker": "editor_footnote",
                    "start": e["start"],
                    "end": e["end"],
                    "span_id": e.get("attached_span_id"),
                    "grading": e.get("grading") or [],
                }
            )

    flags = apply_rule_checks(move, evidence_hits, markers, flags)

    # Attribution: marker-backed only — claimed refs/verdicts need content checks.
    refs = move.get("references") or {}
    has_attr = bool(
        _refs_corroborated(refs, evidence_hits)
        or _verdict_has_ray(markers, move.get("author_verdict_span_ids") or [])
        or _has_speaker(evidence_hits, "SAHABA")
        or _has_speaker(evidence_hits, "TABIIN")
        or _has_family(evidence_hits, "HADITH")
        or _has_family(evidence_hits, "RAY")
        or move.get("primary") in (None, "M_LUGHA", "M_QURAN")
    )
    boundary_ok = "non_contiguous_span_ids" not in flags and not any(
        f.startswith("unknown_span") for f in flags
    )

    scoring = score_move(
        move, flags, evidence_hits, has_function, has_attr, boundary_ok, markers
    )
    marker_ok = scoring.pop("marker_ok", False)

    certainty = move.get("certainty") or "insufficient"
    if (
        certainty == "explicit"
        and move.get("primary")
        and not marker_ok
    ):
        if "rule_explicit_without_marker" not in flags:
            flags.append("rule_explicit_without_marker")
        certainty = "strong"
        # Re-cap score after adding the soft rule flag.
        scoring["total"] = min(scoring["total"], 59)

    certainty = downgrade_certainty(certainty, flags)

    # Mixed span heuristic: move shares a span id with another move — filled later
    mixed_span = False

    route = assign_route(move, certainty, scoring["total"], flags, mixed_span)

    start = by_id[span_ids[0]]["start"] if span_ids else None
    end = by_id[span_ids[-1]]["end"] if span_ids else None

    # Report claimed evidence IDs that exist in the window (or substituted move spans).
    out_evid = (
        [sid for sid in raw_evid if sid in by_id] if raw_evid else evid_ids
    )

    return {
        "move_id": move.get("move_id"),
        "span_ids": span_ids,
        "start": start,
        "end": end,
        "text": rebuilt,
        "primary": move.get("primary"),
        "secondary": move.get("secondary") or [],
        "content_tags": move.get("content_tags") or [],
        "certainty_in": move.get("certainty"),
        "certainty": certainty,
        "evidence_span_ids": out_evid,
        "author_verdict_span_ids": move.get("author_verdict_span_ids") or [],
        "references": move.get("references") or {"verses": [], "hadith": [], "persons": []},
        "alternatives": move.get("alternatives") or [],
        "rationale_ar": move.get("rationale_ar") or "",
        "marker_hits": [
            {
                "span_id": h.get("span_id"),
                "family": h["family"],
                "marker": h["marker"],
                "start": h["start"],
                "end": h["end"],
                **({"role": h["role"]} if "role" in h else {}),
            }
            for h in evidence_hits
            if h["family"] != "EDITOR"
        ],
        "editor_footnote_evidence": [
            e
            for e in (markers.get("editor_footnote_evidence") or [])
            if e.get("attached_span_id") in evid_ids or e.get("attached_span_id") in span_ids
        ],
        "flags": flags,
        "score": scoring,
        "route": route,
        "review_status": "pending",
        "origin": "ai",
    }


def _mark_overlaps(verified_moves: list[dict]) -> None:
    """Flag overlapping span ranges; force specialist on overlaps / mixed spans."""
    for i, a in enumerate(verified_moves):
        a_ids = set(a["span_ids"])
        for j, b in enumerate(verified_moves):
            if i >= j:
                continue
            shared = a_ids & set(b["span_ids"])
            if shared:
                for m in (a, b):
                    if "mixed_or_overlap_spans" not in m["flags"]:
                        m["flags"].append("mixed_or_overlap_spans")
                    m["route"] = "specialist"


def verify_window(annotator: str, window_id: str, moves_payload: dict) -> dict:
    window = _read_json(WINDOWS_DIR / f"{window_id}.json")
    markers = _read_json(MARKERS_DIR / f"{window_id}.json")

    raw_moves = moves_payload.get("moves") or []
    verified = [verify_move(m, window, markers) for m in raw_moves]
    _mark_overlaps(verified)

    # Recompute route after overlap marking (preserve force rules)
    for m in verified:
        m["route"] = assign_route(
            m,
            m["certainty"],
            m["score"]["total"],
            m["flags"],
            "mixed_or_overlap_spans" in m["flags"],
        )

    summary = {
        "window_id": window_id,
        "annotator": annotator,
        "move_count": len(verified),
        "auto_candidate": sum(1 for m in verified if m["route"] == "auto_candidate"),
        "specialist": sum(1 for m in verified if m["route"] == "specialist"),
        "by_primary": {},
        "by_certainty": {},
        "flag_count": sum(len(m["flags"]) for m in verified),
    }
    for m in verified:
        key = str(m["primary"])
        summary["by_primary"][key] = summary["by_primary"].get(key, 0) + 1
        summary["by_certainty"][m["certainty"]] = (
            summary["by_certainty"].get(m["certainty"], 0) + 1
        )

    payload = {
        "window_id": window_id,
        "ayah": window["ayah"],
        "annotator": annotator,
        "source_file": window["source_file"],
        "source_sha256": window.get("source_sha256"),
        "window_start": window["window_start"],
        "window_end": window["window_end"],
        "moves": verified,
        "summary": summary,
    }
    return payload


def write_report(all_summaries: list[dict]) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# تقرير التحقق v2",
        "",
        f"يُبنى من `{MOVES_HINT}` بعد تشغيل المصنّف.",
        "",
    ]
    if not all_summaries:
        lines.append("_لا توجد ملفات moves بعد — لم يُتحقق من شيء._")
        lines.append("")
        lines.append(f"التشغيل المتوقع: ضع مخرجات المصنّف ثم `{VERIFY_CMD_HINT}`.")
    else:
        lines.append("| نافذة | معلّق | حركات | مرشّح آلي | مختص | أعلام |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for s in all_summaries:
            lines.append(
                f"| {s['window_id']} | {s['annotator']} | {s['move_count']} | "
                f"{s['auto_candidate']} | {s['specialist']} | {s['flag_count']} |"
            )
        lines.append("")
    SUMMARY_PATH.write_bytes("\n".join(lines).encode("utf-8"))
    try:
        shown = SUMMARY_PATH.relative_to(ROOT).as_posix()
    except ValueError:
        shown = SUMMARY_PATH.as_posix()
    print(f"wrote {shown}")


def verify_all() -> list[dict]:
    VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    summaries: list[dict] = []
    if not MOVES_DIR.is_dir():
        write_report(summaries)
        print("no moves directory yet — summary only")
        return summaries

    for ann_dir in sorted(p for p in MOVES_DIR.iterdir() if p.is_dir()):
        annotator = ann_dir.name
        for path in sorted(ann_dir.glob("*.json")):
            window_id = path.stem
            moves_payload = _read_json(path)
            # Allow either {"window","moves"} or bare {"moves"}
            if moves_payload.get("window") and moves_payload["window"] != window_id:
                print(
                    f"WARNING: {path} window field "
                    f"{moves_payload.get('window')!r} != {window_id}"
                )
            result = verify_window(annotator, window_id, moves_payload)
            out_dir = VERIFIED_DIR / annotator
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{window_id}.json"
            out.write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
            summaries.append(result["summary"])
            print(
                f"{annotator}/{window_id}: moves={result['summary']['move_count']} "
                f"auto={result['summary']['auto_candidate']} "
                f"spec={result['summary']['specialist']}"
            )
    write_report(summaries)
    return summaries


def verify_payload(annotator: str, window_id: str, moves_payload: dict) -> dict:
    """Public helper for selftest / programmatic use."""
    return verify_window(annotator, window_id, moves_payload)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify classifier moves against markers.")
    p.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help="Base dir with windows/markers/moves (default: data/v2)",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    configure(args.base)
    verify_all()
