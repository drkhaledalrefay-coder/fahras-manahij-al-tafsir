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
    """Normalize model identifier to alphabetic family root.

    Strips version digits, dots, sizes, and suffixes to extract the
    alphabetic family root (e.g. qwen, llama, gemma, mistral, deepseek, phi).

    Examples:
        'llama3.3' -> 'llama'
        'llama3.1' -> 'llama'
        'Qwen2.5:32B' -> 'qwen'
        'qwen2.5-14b-local' -> 'qwen'
        'gemma3' -> 'gemma'
        'gemma2' -> 'gemma'
    """
    if not name:
        return ""
    cleaned = name.strip().lower()
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1]
    m = re.match(r"^([a-z]+)", cleaned)
    if m:
        return m.group(1)
    prefix = re.split(r"[:\-]", cleaned)[0]
    return re.sub(r"[^a-z]", "", prefix)


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


def validate_move_shape(m: any) -> tuple[bool, str | None]:
    """Validate that a verified move meets required shape constraints.

    Requires:
      - 'flags' key present and a list
      - 'score.total' numeric (int or float, not bool)
      - 'route' in {auto_candidate, specialist}
      - 'span_ids' non-empty list

    Returns (is_valid, failure_reason).
    """
    if not isinstance(m, dict):
        return False, "move must be a dict"
    if "flags" not in m or not isinstance(m["flags"], list):
        return False, "missing or non-list flags"
    if "route" not in m or m["route"] not in (ROUTE_AUTO, ROUTE_SPECIALIST):
        return False, "invalid route"
    if "span_ids" not in m or not isinstance(m["span_ids"], list) or len(m["span_ids"]) == 0:
        return False, "missing or empty span_ids"
    score = m.get("score")
    if not isinstance(score, dict):
        return False, "score must be a dict"
    total = score.get("total")
    if not isinstance(total, (int, float)) or isinstance(total, bool):
        return False, "score.total must be numeric"
    return True, None


def find_all_overlapping_reviewer_moves(p_move: dict, r_moves: list[dict]) -> list[dict]:
    """Collect all reviewer moves with overlapping span_ids (non-empty intersection)."""
    if not isinstance(p_move, dict):
        return []
    p_spans = set(p_move.get("span_ids") or []) if isinstance(p_move.get("span_ids"), list) else set()
    if not p_spans:
        return []
    overlapping = []
    for r_move in r_moves:
        if not isinstance(r_move, dict):
            continue
        r_spans = set(r_move.get("span_ids") or []) if isinstance(r_move.get("span_ids"), list) else set()
        if p_spans & r_spans:
            overlapping.append(r_move)
    return overlapping


def find_overlapping_reviewer_move(p_move: dict, r_moves: list[dict]) -> dict | None:
    """Find the best reviewer move with overlapping span_ids (single overlap backward-compatibility)."""
    overlaps = find_all_overlapping_reviewer_moves(p_move, r_moves)
    if not overlaps:
        return None
    p_spans = set(p_move.get("span_ids") or [])
    candidates = []
    for r in overlaps:
        r_spans = set(r.get("span_ids") or [])
        is_exact = p_spans == r_spans
        candidates.append((is_exact, len(p_spans & r_spans), r))
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def evaluate_move(
    p_move: dict,
    r_moves_or_single: list[dict] | dict | None,
    packet_issue: str | None = None,
    is_reused: bool = False,
) -> dict:
    """Deterministic decision for a single proposer move against overlapping reviewer move(s)."""
    if isinstance(r_moves_or_single, list):
        r_list = r_moves_or_single
    elif r_moves_or_single is None:
        r_list = []
    else:
        r_list = [r_moves_or_single]

    # Shape validation on proposer move
    p_valid, _ = validate_move_shape(p_move)
    if not p_valid:
        return {
            "proposer_move_id": p_move.get("move_id") if isinstance(p_move, dict) else None,
            "reviewer_move_id": None,
            "span_ids": p_move.get("span_ids") if isinstance(p_move, dict) and isinstance(p_move.get("span_ids"), list) else [],
            "primary_proposer": p_move.get("primary") if isinstance(p_move, dict) else None,
            "primary_reviewer": None,
            "score_proposer": None,
            "score_reviewer": None,
            "route_proposer": p_move.get("route") if isinstance(p_move, dict) else None,
            "route_reviewer": None,
            "committee_route": ROUTE_SPECIALIST,
            "outcome": "بانتظار المتخصص",
            "abstention_reasons": ["written_abstain"],
            "abstention_ar": format_abstention_ar("written_abstain"),
        }

    # Shape validation on each overlapping reviewer move
    for r in r_list:
        r_valid, _ = validate_move_shape(r)
        if not r_valid:
            return {
                "proposer_move_id": p_move.get("move_id"),
                "reviewer_move_id": r.get("move_id") if isinstance(r, dict) else None,
                "span_ids": p_move.get("span_ids") or [],
                "primary_proposer": p_move.get("primary"),
                "primary_reviewer": r.get("primary") if isinstance(r, dict) else None,
                "score_proposer": p_move.get("score", {}).get("total"),
                "score_reviewer": None,
                "route_proposer": p_move.get("route"),
                "route_reviewer": r.get("route") if isinstance(r, dict) else None,
                "committee_route": ROUTE_SPECIALIST,
                "outcome": "بانتظار المتخصص",
                "abstention_reasons": ["written_abstain"],
                "abstention_ar": format_abstention_ar("written_abstain"),
            }

    p_route = p_move["route"]
    p_primary = p_move.get("primary")
    p_cert = p_move.get("certainty")
    p_score = p_move["score"]["total"]
    p_flags = p_move["flags"]
    p_spans = set(p_move["span_ids"])

    reviewer_ids = [r.get("move_id") for r in r_list if r.get("move_id")]
    r_id_str = ", ".join(str(x) for x in reviewer_ids) if reviewer_ids else None
    reviewer_primaries = [r.get("primary") for r in r_list]
    reviewer_routes = [r.get("route") for r in r_list]
    reviewer_scores = [r["score"]["total"] for r in r_list]

    primary_r_str = (
        reviewer_primaries[0]
        if len(reviewer_primaries) == 1
        else (", ".join(str(x) for x in reviewer_primaries) if reviewer_primaries else None)
    )
    score_r_val = (
        reviewer_scores[0]
        if len(reviewer_scores) == 1
        else (min(reviewer_scores) if reviewer_scores else None)
    )
    route_r_str = (
        reviewer_routes[0]
        if len(reviewer_routes) == 1
        else (
            ROUTE_SPECIALIST
            if any(x == ROUTE_SPECIALIST for x in reviewer_routes)
            else (ROUTE_AUTO if reviewer_routes else None)
        )
    )

    # Committee route = "auto_candidate" ONLY if ALL:
    # (1) route auto_candidate in BOTH (proposer and EVERY overlapping reviewer move);
    # (2) same primary (proposer and EVERY overlapping reviewer move);
    # (3) span overlap (at least one reviewer move, not reused across multiple proposer moves);
    # (4) proposer score.total >= COMMITTEE_THRESHOLD;
    # (5) no flags on either side (proposer and EVERY overlapping reviewer move).
    is_auto = (
        packet_issue is None
        and not is_reused
        and len(r_list) > 0
        and p_route == ROUTE_AUTO
        and bool(p_primary)
        and p_score >= COMMITTEE_THRESHOLD
        and len(p_flags) == 0
        and p_cert in ("explicit", "strong")
        and all(r["route"] == ROUTE_AUTO for r in r_list)
        and all(r.get("primary") == p_primary for r in r_list)
        and all(len(r.get("flags") or []) == 0 for r in r_list)
        and all(r.get("certainty") in ("explicit", "strong") for r in r_list)
    )

    if is_auto:
        return {
            "proposer_move_id": p_move.get("move_id"),
            "reviewer_move_id": r_id_str,
            "span_ids": p_move.get("span_ids") or [],
            "primary_proposer": p_primary,
            "primary_reviewer": primary_r_str,
            "score_proposer": p_score,
            "score_reviewer": score_r_val,
            "route_proposer": p_route,
            "route_reviewer": route_r_str,
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
    # 4. unclear_bounds (no overlap / non_contiguous / mixed spans / reused reviewer move)
    # 5. weak_evidence (weak or score < 85 or evidence flags)

    reason_code: str
    verifier_reason_code: str | None = None

    if not p_primary or p_cert == "insufficient":
        reason_code = "written_abstain"
    elif any(not r.get("primary") or r.get("certainty") == "insufficient" for r in r_list):
        reason_code = "written_abstain"
    elif packet_issue:
        reason_code = "force_specialist"
        verifier_reason_code = packet_issue
    elif p_route == ROUTE_SPECIALIST:
        reason_code = "force_specialist"
        verifier_reason_code = p_move.get("reason_code") or "RULE_FLAG"
    elif any(r.get("route") == ROUTE_SPECIALIST for r in r_list):
        reason_code = "force_specialist"
        spec_r = next(r for r in r_list if r.get("route") == ROUTE_SPECIALIST)
        verifier_reason_code = spec_r.get("reason_code") or "RULE_FLAG"
    elif any(r.get("primary") != p_primary for r in r_list):
        reason_code = "agent_disagree"
    elif (
        len(r_list) == 0
        or is_reused
        or "non_contiguous_span_ids" in p_flags
        or any("non_contiguous_span_ids" in (r.get("flags") or []) for r in r_list)
        or "mixed_or_overlap_spans" in p_flags
        or any("mixed_or_overlap_spans" in (r.get("flags") or []) for r in r_list)
    ):
        reason_code = "unclear_bounds"
    else:
        # weak certainty, score < COMMITTEE_THRESHOLD, or flags
        reason_code = "weak_evidence"

    res = {
        "proposer_move_id": p_move.get("move_id"),
        "reviewer_move_id": r_id_str,
        "span_ids": p_move.get("span_ids") or [],
        "primary_proposer": p_primary,
        "primary_reviewer": primary_r_str,
        "score_proposer": p_score,
        "score_reviewer": score_r_val,
        "route_proposer": p_route,
        "route_reviewer": route_r_str,
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

    # Map each proposer move index to all overlapping reviewer moves
    p_to_r: dict[int, list[dict]] = {}
    r_to_p_count: dict[int, int] = {j: 0 for j in range(len(r_moves))}
    matched_r_indices: set[int] = set()

    for i, p_m in enumerate(p_moves):
        p_spans = set(p_m.get("span_ids") or []) if isinstance(p_m, dict) and isinstance(p_m.get("span_ids"), list) else set()
        overlaps: list[dict] = []
        if p_spans:
            for j, r_m in enumerate(r_moves):
                r_spans = set(r_m.get("span_ids") or []) if isinstance(r_m, dict) and isinstance(r_m.get("span_ids"), list) else set()
                if p_spans & r_spans:
                    overlaps.append(r_m)
                    r_to_p_count[j] += 1
                    matched_r_indices.add(j)
        p_to_r[i] = overlaps

    evaluated_moves = []
    verified_moves = []

    for i, p_m in enumerate(p_moves):
        overlaps = p_to_r[i]
        # Check if any overlapping reviewer move is reused (overlaps > 1 proposer move)
        is_reused = False
        for j, r_m in enumerate(r_moves):
            if r_m in overlaps and r_to_p_count[j] > 1:
                is_reused = True
                break

        m_eval = evaluate_move(p_m, overlaps, packet_issue=packet_issue, is_reused=is_reused)
        evaluated_moves.append(m_eval)

        # Build verified move for verified/committee
        m_copy = dict(p_m) if isinstance(p_m, dict) else {}
        m_copy["route"] = m_eval["committee_route"]
        if m_eval["committee_route"] == ROUTE_AUTO:
            m_copy["reason_code"] = None
        else:
            m_copy["reason_code"] = m_eval.get("verifier_reason_code") or (
                m_eval["abstention_reasons"][0] if m_eval.get("abstention_reasons") else "RULE_FLAG"
            )
        m_copy["committee_reason_code"] = (
            m_eval["abstention_reasons"][0] if m_eval.get("abstention_reasons") else None
        )
        m_copy["committee_abstention_ar"] = m_eval.get("abstention_ar")
        m_copy["outcome"] = m_eval["outcome"]
        verified_moves.append(m_copy)

    # P1-1: Emit every unmatched reviewer move as specialist
    unmatched_r_indices = [j for j in range(len(r_moves)) if j not in matched_r_indices]
    for j in unmatched_r_indices:
        r_m = r_moves[j]
        r_valid, _ = validate_move_shape(r_m) if isinstance(r_m, dict) else (False, "not a dict")
        r_primary = r_m.get("primary") if isinstance(r_m, dict) else None
        r_cert = r_m.get("certainty") if isinstance(r_m, dict) else None

        if packet_issue:
            reason = "force_specialist"
            v_code = packet_issue
        elif not r_valid or not r_primary or r_cert == "insufficient":
            reason = "written_abstain"
            v_code = None
        else:
            # Spans exist but no proposer overlap
            reason = "unclear_bounds"
            v_code = None

        r_score = (
            r_m.get("score", {}).get("total")
            if isinstance(r_m, dict) and isinstance(r_m.get("score"), dict)
            else None
        )
        unmatched_eval = {
            "proposer_move_id": None,
            "reviewer_move_id": r_m.get("move_id") if isinstance(r_m, dict) else None,
            "span_ids": r_m.get("span_ids") if isinstance(r_m, dict) and isinstance(r_m.get("span_ids"), list) else [],
            "primary_proposer": None,
            "primary_reviewer": r_primary,
            "score_proposer": None,
            "score_reviewer": r_score,
            "route_proposer": None,
            "route_reviewer": r_m.get("route") if isinstance(r_m, dict) else None,
            "committee_route": ROUTE_SPECIALIST,
            "outcome": "بانتظار المتخصص",
            "abstention_reasons": [reason],
            "abstention_ar": format_abstention_ar(reason),
        }
        if v_code:
            unmatched_eval["verifier_reason_code"] = v_code
        evaluated_moves.append(unmatched_eval)

        # Also add to verified_moves for verified/committee
        m_copy = dict(r_m) if isinstance(r_m, dict) else {}
        m_copy["route"] = ROUTE_SPECIALIST
        m_copy["reason_code"] = v_code or r_m.get("reason_code") or reason
        m_copy["committee_reason_code"] = reason
        m_copy["committee_abstention_ar"] = format_abstention_ar(reason)
        m_copy["outcome"] = "بانتظار المتخصص"
        verified_moves.append(m_copy)

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

    ayah = p_verified.get("ayah") or r_verified.get("ayah", "")
    surah_match = window_id.split("_")[0] if "_" in window_id else (ayah.split(":")[0] if ":" in ayah else "")
    dorar_link = f"https://dorar.net/tafseer/{surah_match}" if surah_match else "https://dorar.net/tafseer"
    source_file = p_verified.get("source_file") or r_verified.get("source_file", "")
    resolved_runtime = runtime or determine_runtime()

    p_tag = proposer_tag or proposer.replace("-local", "").replace("_", ".")
    r_tag = reviewer_tag or reviewer.replace("-local", "").replace("_", ".")

    committee_payload = {
        "window_id": window_id,
        "tafsir_id": base_path.name,
        "ayah": ayah,
        "source_file": source_file,
        "source_sha256": p_verified.get("source_sha256") or r_verified.get("source_sha256"),
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
        "ayah": ayah,
        "annotator": "committee",
        "source_file": source_file,
        "source_sha256": p_verified.get("source_sha256") or r_verified.get("source_sha256"),
        "window_start": p_verified.get("window_start") if "window_start" in p_verified else r_verified.get("window_start"),
        "window_end": p_verified.get("window_end") if "window_end" in p_verified else r_verified.get("window_end"),
        "packet_sha256": p_verified.get("packet_sha256") or r_verified.get("packet_sha256"),
        "input_assurance": p_verified.get("input_assurance") or r_verified.get("input_assurance"),
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
