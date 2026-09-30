"""Self-test for v2_verify scoring/routing using a hand-written FIXTURE.

The fixture at tests/fixtures/moves_fixture.json must NEVER be loaded by the UI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from v2_verify import verify_payload  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "moves_fixture.json"
WINDOWS_DIR = ROOT / "data" / "v2" / "windows"
MARKERS_DIR = ROOT / "data" / "v2" / "markers"


def main() -> None:
    errors: list[str] = []

    if not FIXTURE.is_file():
        raise SystemExit(f"missing fixture: {FIXTURE}")

    raw = json.loads(FIXTURE.read_bytes().decode("utf-8"))
    if not raw.get("fixture"):
        errors.append("fixture flag missing — refuse unmarked file")
    if "FIXTURE" not in (raw.get("_comment") or "").upper() and not raw.get("fixture"):
        errors.append("fixture not clearly marked")

    window_id = raw["window"]
    if not (WINDOWS_DIR / f"{window_id}.json").is_file():
        raise SystemExit(f"run v2_windows.py first — missing window {window_id}")
    if not (MARKERS_DIR / f"{window_id}.json").is_file():
        raise SystemExit(f"run v2_markers.py first — missing markers {window_id}")

    result = verify_payload("fixture", window_id, raw)
    moves = {m["move_id"]: m for m in result["moves"]}

    # --- expectations ---
    # m01: M_QURAN with markers → should score well, likely auto_candidate
    m01 = moves["m01"]
    if m01["text"] == "":
        errors.append("m01 rebuilt text empty")
    window = json.loads((WINDOWS_DIR / f"{window_id}.json").read_bytes().decode("utf-8"))
    by_id = {s["id"]: s for s in window["spans"]}
    expected = "".join(by_id[sid]["text"] for sid in m01["span_ids"])
    if m01["text"] != expected:
        errors.append("m01 verbatim rebuild mismatch")
    if m01["score"]["parts"]["function_evidence"] != 45:
        errors.append(f"m01 function_evidence != 45: {m01['score']}")
    if m01["score"]["parts"]["marker"] != 25:
        errors.append(f"m01 marker score != 25: {m01['score']}")
    if m01["score"]["total"] < 75:
        errors.append(f"m01 expected score>=75 got {m01['score']['total']}")
    if m01["route"] != "auto_candidate":
        errors.append(f"m01 expected auto_candidate got {m01['route']} flags={m01['flags']}")

    # m02: LUGHA strong
    m02 = moves["m02"]
    if m02["primary"] != "M_LUGHA":
        errors.append("m02 primary changed unexpectedly")
    if m02["score"]["total"] < 50:
        errors.append(f"m02 score too low: {m02['score']['total']}")

    # m03: single-span QURAN
    m03 = moves["m03"]
    if "unknown_span_ids" in m03["flags"]:
        errors.append("m03 unknown spans")
    if m03["score"]["parts"]["marker"] != 25:
        errors.append(f"m03 missing QURAN marker score: {m03['score']} hits={m03['marker_hits']}")

    # m04: intentional bad M_SAHABA → rule flag, downgraded, specialist
    m04 = moves["m04"]
    if not any(f.startswith("rule_M_SAHABA") for f in m04["flags"]):
        errors.append(f"m04 expected SAHABA rule flag, got {m04['flags']}")
    if m04["certainty"] not in ("weak", "insufficient"):
        errors.append(f"m04 certainty should downgrade, got {m04['certainty']}")
    if m04["route"] != "specialist":
        errors.append(f"m04 expected specialist got {m04['route']}")
    if m04["score"]["total"] > 59 and any(f.startswith("rule_") for f in m04["flags"]):
        # capped when rule fails
        errors.append(f"m04 score should be capped ≤59 on rule fail: {m04['score']['total']}")

    # Cap rule: no function evidence → ≤59
    empty = verify_payload(
        "fixture",
        window_id,
        {
            "window": window_id,
            "moves": [
                {
                    "move_id": "m_empty",
                    "span_ids": [],
                    "primary": "M_RAY",
                    "secondary": [],
                    "content_tags": [],
                    "certainty": "explicit",
                    "evidence_span_ids": [],
                    "author_verdict_span_ids": [],
                    "references": {"verses": [], "hadith": [], "persons": []},
                    "alternatives": [],
                    "rationale_ar": "اختبار سقف بلا دليل.",
                }
            ],
        },
    )
    m_empty = empty["moves"][0]
    if m_empty["score"]["total"] > 59:
        errors.append(f"empty evidence score cap failed: {m_empty['score']['total']}")
    if m_empty["route"] != "specialist":
        errors.append("empty evidence should route specialist")

    if errors:
        print("SELFTEST FAIL")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)

    print("SELFTEST PASS")
    print(
        f"  m01 score={m01['score']['total']} route={m01['route']} "
        f"certainty={m01['certainty']}"
    )
    print(
        f"  m02 score={m02['score']['total']} route={m02['route']} "
        f"certainty={m02['certainty']}"
    )
    print(
        f"  m03 score={m03['score']['total']} route={m03['route']} "
        f"certainty={m03['certainty']}"
    )
    print(
        f"  m04 score={m04['score']['total']} route={m04['route']} "
        f"certainty={m04['certainty']} flags={m04['flags']}"
    )
    print(f"  m_empty score={m_empty['score']['total']} route={m_empty['route']}")


if __name__ == "__main__":
    main()
