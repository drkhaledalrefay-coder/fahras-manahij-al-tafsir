"""Deterministic Committee Chair (threshold 85) for tafsir methodology tagging.

Rides on deterministic verified outputs (v2_verify) from two different model families.
Evaluates consensus on span boundaries, primary methodology, score >= 85, and lack of flags.
Outputs:
  - <base>/committee/<window>.json (committee decision schema)
  - <base>/verified/committee/<window>.json (verified-file shape for existing UI)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from grounding_contract import (
    COMMITTEE_CAPTION,
    COMMITTEE_REASON_CODES,
    COMMITTEE_THRESHOLD,
    ROUTE_AUTO,
    ROUTE_SPECIALIST,
)


class SameFamilyError(ValueError):
    """Raised when proposer and reviewer belong to the same model family."""
    pass


DEFAULT_ABSTENTION_AR: dict[str, str] = {
    "written_abstain": "امتناع بسبب مكتوب: المنهج الرئيسي فارغ أو يقين المصنّف غير كافٍ.",
    "force_specialist": "إحالة الفاحص: أحد الطرفين أُحيل إلى متخصص في التحقق الحتمي أو حدث خلل في بصمة الحزمة.",
    "agent_disagree": "اختلاف الوكلاء: اختلف المصنّف والمدقّق في تعيين المنهج الرئيسي للمقطع.",
    "unclear_bounds": "حدود غير واضحة: لا يوجد تقاطع كافٍ في حدود الأجزاء بين النموذجين أو رُصد عدم اتصال في الأجزاء.",
    "weak_evidence": "دليل ضعيف: درجة المصنّف دون عتبة اللجنة (85) أو اليقين ضعيف أو رُصدت أعلام على الدليل.",
}


def extract_family(name: str) -> str:
    """Extract model family prefix before ':' or '-'.

    Examples:
        'qwen2.5:14b' -> 'qwen2.5'
        'qwen2.5-14b-local' -> 'qwen2.5'
        'gemma2:9b' -> 'gemma2'
        'gemma2-9b-local' -> 'gemma2'
        'deepseek-chat' -> 'deepseek'
    """
    if not name:
        return ""
    prefix = re.split(r"[:\-]", name)[0].strip().lower()
    return prefix.replace("_", ".")


def check_different_families(proposer: str, reviewer: str) -> None:
    """Refuse if proposer and reviewer belong to the same model family."""
    fam_p = extract_family(proposer)
    fam_r = extract_family(reviewer)
    if fam_p and fam_r and fam_p == fam_r:
        raise SameFamilyError(
            f"عائلتان مختلفتان: Proposer '{proposer}' and reviewer '{reviewer}' "
            f"belong to the same model family '{fam_p}'."
        )


def determine_runtime(base_url: str | None = None) -> str:
    """Determine runtime mode.

    'ollama-local' only if LLM_BASE_URL host is localhost/127.0.0.1,
    else 'hosted (<host>)' with host only, never keys.
    """
    url = os.environ.get("LLM_BASE_URL", "") if base_url is None else base_url
    if not url:
        return "ollama-local"
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
    except Exception:
        host = ""
    if host in ("localhost", "127.0.0.1", "::1") or not host:
        return "ollama-local"
    return f"hosted ({host})"


def llm_reword_abstention_hook(code: str, fallback_ar: str, details: dict | None = None) -> str:
    """Hook for an optional later LLM rewording step (e.g. qwen2.5:14b).

    Must never change the route decision.
    Currently returns the deterministic fixed fallback.
    """
    return fallback_ar


def format_abstention_ar(code: str, details: dict | None = None) -> str:
    """Deterministic fixed Arabic sentence per committee reason code."""
    fallback = DEFAULT_ABSTENTION_AR.get(code, f"امتناع: {code}")
    return llm_reword_abstention_hook(code, fallback, details)


def find_overlapping_reviewer_move(p_move: dict, r_moves: list[dict]) -> dict | None:
    """Find the best reviewer move with overlapping span_ids (same set or non-empty intersection)."""
    p_spans = set(p_move.get("span_ids") or [])
    if not p_spans:
        return None
    candidates: list[tuple[bool, int, dict]] = []
    for r_move in r_moves:
        r_spans = set(r_move.get("span_ids") or [])
        intersection = p_spans & r_spans
        if intersection:
            is_exact = p_spans == r_spans
            overlap_count = len(intersection)
            candidates.append((is_exact, overlap_count, r_move))
    if not candidates:
        return None
    # Prefer exact span set match, then largest overlap count
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def evaluate_move(
    p_move: dict,
    r_move: dict | None,
    packet_issue: str | None = None,
) -> dict:
    """Deterministic decision for a single proposer move against the best matching reviewer move."""
    p_route = p_move.get("route")
    p_primary = p_move.get("primary")
    p_cert = p_move.get("certainty")
    p_score_obj = p_move.get("score")
    if isinstance(p_score_obj, dict):
        p_score = p_score_obj.get("total", 0)
    elif isinstance(p_score_obj, (int, float)):
        p_score = int(p_score_obj)
    else:
        p_score = 0

    p_flags = list(p_move.get("flags") or [])
    p_spans = set(p_move.get("span_ids") or [])

    r_route = r_move.get("route") if r_move else None
    r_primary = r_move.get("primary") if r_move else None
    r_cert = r_move.get("certainty") if r_move else None
    r_score_obj = r_move.get("score") if r_move else None
    if isinstance(r_score_obj, dict):
        r_score = r_score_obj.get("total", 0)
    elif isinstance(r_score_obj, (int, float)):
        r_score = int(r_score_obj)
    else:
        r_score = None

    r_flags = list(r_move.get("flags") or []) if r_move else []
    r_spans = set(r_move.get("span_ids") or []) if r_move else set()

    has_overlap = bool(p_spans & r_spans) if r_move else False

    # Committee route = "auto_candidate" ONLY if ALL:
    # (1) route auto_candidate in BOTH;
    # (2) same primary;
    # (3) span overlap;
    # (4) proposer score.total >= COMMITTEE_THRESHOLD;
    # (5) no flags on either side.
    is_auto = (
        packet_issue is None
        and p_route == ROUTE_AUTO
        and r_route == ROUTE_AUTO
        and bool(p_primary)
        and p_primary == r_primary
        and has_overlap
        and p_score >= COMMITTEE_THRESHOLD
        and len(p_flags) == 0
        and len(r_flags) == 0
        and p_cert in ("explicit", "strong")
        and (r_cert in ("explicit", "strong") if r_cert else False)
    )

    if is_auto:
        return {
            "proposer_move_id": p_move.get("move_id"),
            "reviewer_move_id": r_move.get("move_id") if r_move else None,
            "span_ids": p_move.get("span_ids") or [],
            "primary_proposer": p_primary,
            "primary_reviewer": r_primary,
            "score_proposer": p_score,
            "score_reviewer": r_score,
            "route_proposer": p_route,
            "route_reviewer": r_route,
            "committee_route": ROUTE_AUTO,
            "outcome": "مرشح للقبول",
            "abstention_reasons": [],
            "abstention_ar": None,
        }

    # Otherwise specialist: exactly ONE code from COMMITTEE_REASON_CODES,
    # first applicable in order:
    # 1. written_abstain (insufficient certainty or empty primary)
    # 2. force_specialist (packet hash issue OR any side already specialist from verifier)
    # 3. agent_disagree (different primary)
    # 4. unclear_bounds (no overlap / non_contiguous / mixed spans)
    # 5. weak_evidence (weak or score < 85 or evidence flags)

    reason_code: str
    verifier_reason_code: str | None = None

    if packet_issue:
        reason_code = "force_specialist"
        verifier_reason_code = packet_issue
    elif not p_primary or p_cert == "insufficient":
        reason_code = "written_abstain"
    elif r_move and (not r_primary or r_cert == "insufficient"):
        reason_code = "written_abstain"
    elif p_route == ROUTE_SPECIALIST or (r_move and r_route == ROUTE_SPECIALIST):
        reason_code = "force_specialist"
        if p_route == ROUTE_SPECIALIST:
            verifier_reason_code = p_move.get("reason_code") or "RULE_FLAG"
        else:
            verifier_reason_code = (r_move.get("reason_code") if r_move else None) or "RULE_FLAG"
    elif r_move and p_primary != r_primary:
        reason_code = "agent_disagree"
    elif (
        not r_move
        or not has_overlap
        or "non_contiguous_span_ids" in p_flags
        or "non_contiguous_span_ids" in r_flags
        or "mixed_or_overlap_spans" in p_flags
        or "mixed_or_overlap_spans" in r_flags
    ):
        reason_code = "unclear_bounds"
    else:
        # weak certainty, score < COMMITTEE_THRESHOLD, or flags
        reason_code = "weak_evidence"

    res = {
        "proposer_move_id": p_move.get("move_id"),
        "reviewer_move_id": r_move.get("move_id") if r_move else None,
        "span_ids": p_move.get("span_ids") or [],
        "primary_proposer": p_primary,
        "primary_reviewer": r_primary,
        "score_proposer": p_score,
        "score_reviewer": r_score,
        "route_proposer": p_route,
        "route_reviewer": r_route,
        "committee_route": ROUTE_SPECIALIST,
        "outcome": "بانتظار المتخصص",
        "abstention_reasons": [reason_code],
        "abstention_ar": format_abstention_ar(reason_code),
    }
    if verifier_reason_code:
        res["verifier_reason_code"] = verifier_reason_code
    return res


def evaluate_window(
    base: Path | str,
    proposer: str,
    reviewer: str,
    window_id: str,
    *,
    proposer_tag: str | None = None,
    reviewer_tag: str | None = None,
    proposer_quant: str = "Q4_K_M",
    reviewer_quant: str = "Q4_K_M",
    runtime: str | None = None,
) -> tuple[dict, dict]:
    """Evaluate one window with proposer and reviewer outputs.

    Writes:
      <base>/committee/<window_id>.json
      <base>/verified/committee/<window_id>.json
    Never modifies input verified files.
    """
    check_different_families(proposer, reviewer)
    base_path = Path(base).resolve()
    p_file = base_path / "verified" / proposer / f"{window_id}.json"
    r_file = base_path / "verified" / reviewer / f"{window_id}.json"

    if not p_file.is_file():
        raise FileNotFoundError(f"Missing proposer verified file: {p_file}")
    if not r_file.is_file():
        raise FileNotFoundError(f"Missing reviewer verified file: {r_file}")

    p_verified = json.loads(p_file.read_text(encoding="utf-8"))
    r_verified = json.loads(r_file.read_text(encoding="utf-8"))

    # Packet binding check
    p_sha = p_verified.get("packet_sha256")
    r_sha = r_verified.get("packet_sha256")
    packet_issue: str | None = None
    if not p_sha or not r_sha:
        packet_issue = "PACKET_HASH_MISSING"
    elif p_sha != r_sha:
        packet_issue = "PACKET_HASH_MISMATCH"

    p_moves = p_verified.get("moves") or []
    r_moves = r_verified.get("moves") or []

    evaluated_moves = []
    for p_move in p_moves:
        best_r = find_overlapping_reviewer_move(p_move, r_moves)
        m_eval = evaluate_move(p_move, best_r, packet_issue=packet_issue)
        evaluated_moves.append(m_eval)

    by_abstention = {code: 0 for code in COMMITTEE_REASON_CODES}
    for m in evaluated_moves:
        for r in m.get("abstention_reasons", []):
            if r in by_abstention:
                by_abstention[r] += 1

    summary = {
        "move_count": len(evaluated_moves),
        "auto_candidate": sum(1 for m in evaluated_moves if m["committee_route"] == ROUTE_AUTO),
        "specialist": sum(1 for m in evaluated_moves if m["committee_route"] == ROUTE_SPECIALIST),
        "by_abstention_reason": by_abstention,
        "caption": COMMITTEE_CAPTION,
    }

    ayah = p_verified.get("ayah", "")
    surah_match = window_id.split("_")[0] if "_" in window_id else (ayah.split(":")[0] if ":" in ayah else "")
    dorar_link = f"https://dorar.net/tafseer/{surah_match}" if surah_match else "https://dorar.net/tafseer"
    source_file = p_verified.get("source_file", "")
    resolved_runtime = runtime or determine_runtime()

    p_tag = proposer_tag or proposer.replace("-local", "").replace("_", ".")
    r_tag = reviewer_tag or reviewer.replace("-local", "").replace("_", ".")

    committee_payload = {
        "window_id": window_id,
        "tafsir_id": base_path.name,
        "ayah": ayah,
        "source_file": source_file,
        "source_sha256": p_verified.get("source_sha256"),
        "runtime": resolved_runtime,
        "models": {
            "proposer": {"tag": p_tag, "annotator": proposer, "quant": proposer_quant},
            "reviewer": {"tag": r_tag, "annotator": reviewer, "quant": reviewer_quant},
        },
        "source_links": {
            "tafsir_center_dataset": "https://huggingface.co/datasets/tafsircenter/tafsir-mcp-data",
            "dorar_surah": dorar_link,
            "local_source_file": source_file,
        },
        "moves": evaluated_moves,
        "summary": summary,
    }

    # Build verified-file shape for existing UI readers
    verified_moves = []
    for p_m, c_m in zip(p_moves, evaluated_moves):
        m_copy = dict(p_m)
        m_copy["route"] = c_m["committee_route"]
        if c_m["committee_route"] == ROUTE_AUTO:
            m_copy["reason_code"] = None
        else:
            m_copy["reason_code"] = c_m.get("verifier_reason_code") or (
                c_m["abstention_reasons"][0] if c_m.get("abstention_reasons") else "RULE_FLAG"
            )
        m_copy["committee_reason_code"] = (
            c_m["abstention_reasons"][0] if c_m.get("abstention_reasons") else None
        )
        m_copy["committee_abstention_ar"] = c_m.get("abstention_ar")
        m_copy["outcome"] = c_m["outcome"]
        verified_moves.append(m_copy)

    verified_summary = {
        "window_id": window_id,
        "annotator": "committee",
        "move_count": len(verified_moves),
        "auto_candidate": sum(1 for m in verified_moves if m["route"] == ROUTE_AUTO),
        "specialist": sum(1 for m in verified_moves if m["route"] == ROUTE_SPECIALIST),
        "by_primary": {},
        "by_certainty": {},
        "by_reason": {},
        "flag_count": sum(len(m.get("flags") or []) for m in verified_moves),
    }
    for m in verified_moves:
        key = str(m.get("primary"))
        verified_summary["by_primary"][key] = verified_summary["by_primary"].get(key, 0) + 1
        cert = str(m.get("certainty", ""))
        verified_summary["by_certainty"][cert] = verified_summary["by_certainty"].get(cert, 0) + 1
        rkey = str(m.get("reason_code"))
        verified_summary["by_reason"][rkey] = verified_summary["by_reason"].get(rkey, 0) + 1

    verified_committee_payload = {
        "window_id": window_id,
        "ayah": p_verified.get("ayah"),
        "annotator": "committee",
        "source_file": p_verified.get("source_file"),
        "source_sha256": p_verified.get("source_sha256"),
        "window_start": p_verified.get("window_start"),
        "window_end": p_verified.get("window_end"),
        "packet_sha256": p_verified.get("packet_sha256"),
        "input_assurance": p_verified.get("input_assurance"),
        "moves": verified_moves,
        "summary": verified_summary,
    }

    out_committee = base_path / "committee" / f"{window_id}.json"
    out_verified = base_path / "verified" / "committee" / f"{window_id}.json"
    out_committee.parent.mkdir(parents=True, exist_ok=True)
    out_verified.parent.mkdir(parents=True, exist_ok=True)

    out_committee.write_text(
        json.dumps(committee_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out_verified.write_text(
        json.dumps(verified_committee_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return committee_payload, verified_committee_payload


def run_chair(
    base: Path | str,
    proposer: str,
    reviewer: str,
    window: str | None = None,
    all_windows: bool = False,
    proposer_tag: str | None = None,
    reviewer_tag: str | None = None,
    proposer_quant: str = "Q4_K_M",
    reviewer_quant: str = "Q4_K_M",
) -> list[tuple[dict, dict]]:
    """Run committee chair on one or all windows."""
    check_different_families(proposer, reviewer)
    base_path = Path(base).resolve()
    p_dir = base_path / "verified" / proposer
    if not p_dir.is_dir():
        raise FileNotFoundError(f"Proposer verified directory not found: {p_dir}")
    r_dir = base_path / "verified" / reviewer
    if not r_dir.is_dir():
        raise FileNotFoundError(f"Reviewer verified directory not found: {r_dir}")

    if window:
        windows = [window]
    elif all_windows:
        windows = [p.stem for p in sorted(p_dir.glob("*.json"))]
    else:
        raise ValueError("Must specify either --window W or --all")

    results = []
    for w in windows:
        p_path = p_dir / f"{w}.json"
        r_path = r_dir / f"{w}.json"
        if not p_path.is_file():
            raise FileNotFoundError(f"Missing proposer verified file: {p_path}")
        if not r_path.is_file():
            raise FileNotFoundError(f"Missing reviewer verified file: {r_path}")
        res = evaluate_window(
            base=base_path,
            proposer=proposer,
            reviewer=reviewer,
            window_id=w,
            proposer_tag=proposer_tag,
            reviewer_tag=reviewer_tag,
            proposer_quant=proposer_quant,
            reviewer_quant=reviewer_quant,
        )
        results.append(res)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic Committee Chair (threshold 85) riding on verified outputs."
    )
    parser.add_argument(
        "--base",
        required=True,
        help="Base directory containing verified/<annotator>/ (e.g. data/nur/al_tabari)",
    )
    parser.add_argument(
        "--proposer",
        required=True,
        help="Proposer annotator folder under verified/ (e.g. qwen2.5-14b-local)",
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Reviewer annotator folder under verified/ (e.g. gemma2-9b-local)",
    )
    window_group = parser.add_mutually_exclusive_group(required=True)
    window_group.add_argument(
        "--window",
        help="Single window ID to evaluate (e.g. 24_1)",
    )
    window_group.add_argument(
        "--all",
        action="store_true",
        help="Evaluate all windows found in verified/<proposer>/",
    )
    parser.add_argument("--proposer-tag", help="Model tag for proposer (e.g. qwen2.5:14b)")
    parser.add_argument("--reviewer-tag", help="Model tag for reviewer (e.g. gemma2:9b)")
    parser.add_argument(
        "--proposer-quant",
        default="Q4_K_M",
        help="Quantization tag for proposer (default: Q4_K_M)",
    )
    parser.add_argument(
        "--reviewer-quant",
        default="Q4_K_M",
        help="Quantization tag for reviewer (default: Q4_K_M)",
    )

    args = parser.parse_args(argv)

    try:
        check_different_families(args.proposer, args.reviewer)
    except SameFamilyError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    try:
        results = run_chair(
            base=args.base,
            proposer=args.proposer,
            reviewer=args.reviewer,
            window=args.window,
            all_windows=args.all,
            proposer_tag=args.proposer_tag,
            reviewer_tag=args.reviewer_tag,
            proposer_quant=args.proposer_quant,
            reviewer_quant=args.reviewer_quant,
        )
    except Exception as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    total_auto = sum(r[0]["summary"]["auto_candidate"] for r in results)
    total_spec = sum(r[0]["summary"]["specialist"] for r in results)
    total_moves = sum(r[0]["summary"]["move_count"] for r in results)
    print(
        f"Committee Chair: processed {len(results)} window(s), "
        f"{total_moves} move(s): {total_auto} auto_candidate, {total_spec} specialist. "
        f"({COMMITTEE_CAPTION})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
