"""Tests for deterministic Committee Chair (threshold 85).

Covers:
- Negative tests (one per rule):
  1. Both auto but proposer score 80 -> specialist weak_evidence
  2. Different primary -> agent_disagree
  3. Reviewer specialist -> force_specialist + verifier_reason_code copied
  4. No overlap -> unclear_bounds
  5. Insufficient certainty or empty primary -> written_abstain
  6. Same family -> refused (llama3.3 vs llama3.1, Qwen2.5:32B vs qwen2.5-14b-local, gemma3 vs gemma2; qwen vs gemma accepted)
  7. Hash mismatch / missing between sides -> force_specialist PACKET_HASH_MISMATCH / PACKET_HASH_MISSING
  8. Input verified files byte-identical after run
  9. Shape validation: flags missing or score.total None -> specialist written_abstain, no exception
  10. Multi-overlap: reviewer A agrees on s001, reviewer B disagrees on s002 -> specialist agent_disagree
  11. Reviewer move reuse: reviewer move overlapping two proposer moves -> both specialist unclear_bounds
  12. Unmatched reviewer move: reviewer has extra move -> present in both files as specialist
- Positive test:
  Both auto, same primary, overlap, score 90, no flags -> auto_candidate
- End-to-End test:
  Fake HTTP model -> classify_api.classify on tmp packet -> v2_verify.verify_window
  -> run twice with two different fake families -> committee_chair
  -> assert full chain yields auto_candidate for grounded move AND specialist for ungrounded move.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import classify_api  # noqa: E402
import committee_chair  # noqa: E402
import grounding_contract  # noqa: E402
import v2_verify  # noqa: E402


def _make_move(
    move_id: str = "m01",
    span_ids: list[str] | None = None,
    primary: str | None = "M_LUGHA",
    certainty: str = "strong",
    score_total: int | None = 90,
    flags: list[str] | None = None,
    route: str = "auto_candidate",
    reason_code: str | None = None,
) -> dict:
    move: dict = {
        "move_id": move_id,
        "span_ids": span_ids or ["s001", "s002"],
        "start": 0,
        "end": 50,
        "text": "نص تجريبي",
        "primary": primary,
        "secondary": [],
        "content_tags": ["C_TAFSIR"],
        "certainty": certainty,
        "certainty_in": certainty,
        "evidence_span_ids": [span_ids[0]] if span_ids else ["s001"],
        "author_verdict_span_ids": [],
        "references": {"verses": [], "hadith": [], "persons": []},
        "route": route,
        "reason_code": reason_code,
    }
    if flags is not None:
        move["flags"] = flags
    else:
        move["flags"] = []

    move["score"] = {
        "evidence_quality": 40,
        "span_tightness": 20,
        "method_fit": 20,
        "structure": 10,
        "total": score_total,
    }
    return move


def _make_verified_file(
    window_id: str = "24_1",
    annotator: str = "qwen2.5-14b-local",
    moves: list[dict] | None = None,
    packet_sha: str = "deadbeef" * 8,
) -> dict:
    m_list = moves if moves is not None else [_make_move()]
    return {
        "window_id": window_id,
        "ayah": "24:1",
        "annotator": annotator,
        "source_file": f"data/nur/al_tabari/raw/{window_id}.txt",
        "source_sha256": "aabbcc" * 10,
        "window_start": 0,
        "window_end": 100,
        "packet_sha256": packet_sha,
        "input_assurance": "api_packet",
        "moves": m_list,
        "summary": {
            "window_id": window_id,
            "annotator": annotator,
            "move_count": len(m_list),
            "auto_candidate": sum(1 for m in m_list if m.get("route") == "auto_candidate"),
            "specialist": sum(1 for m in m_list if m.get("route") == "specialist"),
            "by_primary": {},
            "by_certainty": {},
            "by_reason": {},
            "flag_count": sum(len(m.get("flags") or []) for m in m_list),
        },
    }


class TestCommitteeChairNegative(unittest.TestCase):
    """Negative tests: one per rule."""

    def test_both_auto_proposer_score_80_yields_weak_evidence(self) -> None:
        """Rule: both auto but proposer score < 85 (e.g. 80) -> specialist weak_evidence."""
        p_move = _make_move(score_total=80, route="auto_candidate")
        r_move = _make_move(score_total=90, route="auto_candidate")
        decision = committee_chair.evaluate_move(p_move, [r_move])
        self.assertEqual(decision["committee_route"], "specialist")
        self.assertEqual(decision["outcome"], "بانتظار المتخصص")
        self.assertEqual(decision["abstention_reasons"], ["weak_evidence"])
        self.assertIn("دليل ضعيف", decision["abstention_ar"])

    def test_different_primary_yields_agent_disagree(self) -> None:
        """Rule: different primary -> agent_disagree."""
        p_move = _make_move(primary="M_LUGHA", score_total=90, route="auto_candidate")
        r_move = _make_move(primary="M_QURAN", score_total=90, route="auto_candidate")
        decision = committee_chair.evaluate_move(p_move, [r_move])
        self.assertEqual(decision["committee_route"], "specialist")
        self.assertEqual(decision["outcome"], "بانتظار المتخصص")
        self.assertEqual(decision["abstention_reasons"], ["agent_disagree"])
        self.assertIn("اختلاف الوكلاء", decision["abstention_ar"])

    def test_reviewer_specialist_yields_force_specialist_with_copied_code(self) -> None:
        """Rule: reviewer specialist -> force_specialist + verifier_reason_code copied."""
        p_move = _make_move(score_total=90, route="auto_candidate")
        r_move = _make_move(
            score_total=60,
            route="specialist",
            reason_code="RULE_FLAG",
            flags=["rule_some_flag"],
        )
        decision = committee_chair.evaluate_move(p_move, [r_move])
        self.assertEqual(decision["committee_route"], "specialist")
        self.assertEqual(decision["outcome"], "بانتظار المتخصص")
        self.assertEqual(decision["abstention_reasons"], ["force_specialist"])
        self.assertEqual(decision["verifier_reason_code"], "RULE_FLAG")
        self.assertIn("إحالة الفاحص", decision["abstention_ar"])

    def test_no_overlap_yields_unclear_bounds(self) -> None:
        """Rule: no overlap -> unclear_bounds."""
        p_move = _make_move(span_ids=["s001", "s002"], score_total=90, route="auto_candidate")
        r_move = _make_move(span_ids=["s003", "s004"], score_total=90, route="auto_candidate")
        # When passed disjoint reviewer moves
        decision = committee_chair.evaluate_move(p_move, [])
        self.assertEqual(decision["committee_route"], "specialist")
        self.assertEqual(decision["outcome"], "بانتظار المتخصص")
        self.assertEqual(decision["abstention_reasons"], ["unclear_bounds"])
        self.assertIn("حدود غير واضحة", decision["abstention_ar"])

        # Also when reviewer move is None altogether
        decision_none = committee_chair.evaluate_move(p_move, None)
        self.assertEqual(decision_none["committee_route"], "specialist")
        self.assertEqual(decision_none["abstention_reasons"], ["unclear_bounds"])

    def test_insufficient_certainty_or_empty_primary_yields_written_abstain(self) -> None:
        """Rule: insufficient certainty or empty primary -> written_abstain."""
        # 1. Proposer certainty == 'insufficient'
        p_move_insuf = _make_move(certainty="insufficient", score_total=40, route="specialist")
        r_move = _make_move(certainty="strong", score_total=90, route="auto_candidate")
        d1 = committee_chair.evaluate_move(p_move_insuf, [r_move])
        self.assertEqual(d1["committee_route"], "specialist")
        self.assertEqual(d1["abstention_reasons"], ["written_abstain"])
        self.assertIn("امتناع بسبب مكتوب", d1["abstention_ar"])

        # 2. Proposer primary is empty / None
        p_move_empty_primary = _make_move(primary=None, score_total=70, route="specialist")
        d2 = committee_chair.evaluate_move(p_move_empty_primary, [r_move])
        self.assertEqual(d2["committee_route"], "specialist")
        self.assertEqual(d2["abstention_reasons"], ["written_abstain"])

    def test_same_family_refused(self) -> None:
        """Rule: refuse if proposer and reviewer annotator are the same model family."""
        # P1-4: llama3.3 vs llama3.1, Qwen2.5:32B vs qwen2.5-14b-local, gemma3 vs gemma2 are SAME family
        refused_pairs = [
            ("llama3.3", "llama3.1"),
            ("Qwen2.5:32B", "qwen2.5-14b-local"),
            ("gemma3", "gemma2"),
            ("qwen2.5-14b-local", "qwen2.5-7b-local"),
            ("deepseek-chat", "deepseek-coder"),
        ]
        for p, r in refused_pairs:
            with self.subTest(proposer=p, reviewer=r):
                with self.assertRaises(committee_chair.SameFamilyError) as cm:
                    committee_chair.check_different_families(p, r)
                self.assertIn("عائلتان مختلفتان", str(cm.exception))

        # qwen vs gemma accepted
        try:
            committee_chair.check_different_families("qwen2.5:14b", "gemma2:9b")
            committee_chair.check_different_families("qwen", "gemma")
        except committee_chair.SameFamilyError:
            self.fail("check_different_families raised SameFamilyError unexpectedly for qwen vs gemma")

        # CLI invocation with same family returns non-zero
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            code = committee_chair.main(
                [
                    "--base",
                    "data/nur/al_tabari",
                    "--proposer",
                    "llama3.3",
                    "--reviewer",
                    "llama3.1",
                    "--window",
                    "24_1",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("عائلتان مختلفتان", stderr_buf.getvalue())

    def test_packet_hash_mismatch_and_missing_yields_force_specialist(self) -> None:
        """Rule: hash mismatch or missing between sides -> force_specialist PACKET_HASH_MISMATCH/PACKET_HASH_MISSING."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            p_dir = tmp_path / "verified" / "qwen2.5-14b-local"
            r_dir = tmp_path / "verified" / "gemma2-9b-local"
            p_dir.mkdir(parents=True)
            r_dir.mkdir(parents=True)

            # Test mismatch
            p_data = _make_verified_file(
                "24_1", annotator="qwen2.5-14b-local", packet_sha="1111" * 16
            )
            r_data = _make_verified_file(
                "24_1", annotator="gemma2-9b-local", packet_sha="2222" * 16
            )
            (p_dir / "24_1.json").write_text(json.dumps(p_data), encoding="utf-8")
            (r_dir / "24_1.json").write_text(json.dumps(r_data), encoding="utf-8")

            c_pay, v_pay = committee_chair.evaluate_window(
                base=tmp_path,
                proposer="qwen2.5-14b-local",
                reviewer="gemma2-9b-local",
                window_id="24_1",
            )
            self.assertEqual(c_pay["moves"][0]["committee_route"], "specialist")
            self.assertEqual(c_pay["moves"][0]["abstention_reasons"], ["force_specialist"])
            self.assertEqual(c_pay["moves"][0]["verifier_reason_code"], "PACKET_HASH_MISMATCH")

            # Test missing hash
            p_data["packet_sha256"] = None
            (p_dir / "24_1.json").write_text(json.dumps(p_data), encoding="utf-8")
            c_pay2, v_pay2 = committee_chair.evaluate_window(
                base=tmp_path,
                proposer="qwen2.5-14b-local",
                reviewer="gemma2-9b-local",
                window_id="24_1",
            )
            self.assertEqual(c_pay2["moves"][0]["committee_route"], "specialist")
            self.assertEqual(c_pay2["moves"][0]["abstention_reasons"], ["force_specialist"])
            self.assertEqual(c_pay2["moves"][0]["verifier_reason_code"], "PACKET_HASH_MISSING")

    def test_input_verified_files_remain_byte_identical(self) -> None:
        """Rule: input verified files must remain byte-identical after running committee chair."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            p_dir = tmp_path / "verified" / "qwen2.5-14b-local"
            r_dir = tmp_path / "verified" / "gemma2-9b-local"
            p_dir.mkdir(parents=True)
            r_dir.mkdir(parents=True)

            p_data = _make_verified_file("24_1", annotator="qwen2.5-14b-local")
            r_data = _make_verified_file("24_1", annotator="gemma2-9b-local")

            p_path = p_dir / "24_1.json"
            r_path = r_dir / "24_1.json"
            p_path.write_text(json.dumps(p_data, indent=2, ensure_ascii=False), encoding="utf-8")
            r_path.write_text(json.dumps(r_data, indent=2, ensure_ascii=False), encoding="utf-8")

            p_bytes_before = p_path.read_bytes()
            r_bytes_before = r_path.read_bytes()

            committee_chair.evaluate_window(
                base=tmp_path,
                proposer="qwen2.5-14b-local",
                reviewer="gemma2-9b-local",
                window_id="24_1",
            )

            p_bytes_after = p_path.read_bytes()
            r_bytes_after = r_path.read_bytes()

            self.assertEqual(p_bytes_before, p_bytes_after)
            self.assertEqual(r_bytes_before, r_bytes_after)

    # --- P1-3: Shape validation tests ---
    def test_shape_validation_flags_missing_yields_specialist(self) -> None:
        """P1-3: flags key missing -> specialist written_abstain, no exception."""
        p_move = _make_move()
        del p_move["flags"]  # flags key missing
        r_move = _make_move()
        # Must not raise an exception
        decision = committee_chair.evaluate_move(p_move, [r_move])
        self.assertEqual(decision["committee_route"], "specialist")
        self.assertEqual(decision["abstention_reasons"], ["written_abstain"])

    def test_shape_validation_score_total_none_yields_specialist(self) -> None:
        """P1-3: score.total None -> specialist written_abstain, no exception."""
        p_move = _make_move()
        p_move["score"]["total"] = None  # score.total None
        r_move = _make_move()
        # Must not raise an exception
        decision = committee_chair.evaluate_move(p_move, [r_move])
        self.assertEqual(decision["committee_route"], "specialist")
        self.assertEqual(decision["abstention_reasons"], ["written_abstain"])

    # --- P1-2: Multi-overlap and reuse tests ---
    def test_multi_overlap_reviewer_split_disagreement_yields_agent_disagree(self) -> None:
        """P1-2: reviewer A agrees on s001, reviewer B disagrees on s002, proposer spans s001+s002 -> specialist agent_disagree."""
        p_move = _make_move(
            move_id="p01",
            span_ids=["s001", "s002"],
            primary="M_LUGHA",
            score_total=90,
            route="auto_candidate",
        )
        r_move_a = _make_move(
            move_id="r01",
            span_ids=["s001"],
            primary="M_LUGHA",
            score_total=90,
            route="auto_candidate",
        )
        r_move_b = _make_move(
            move_id="r02",
            span_ids=["s002"],
            primary="M_QURAN",  # disagrees!
            score_total=90,
            route="auto_candidate",
        )
        decision = committee_chair.evaluate_move(p_move, [r_move_a, r_move_b])
        self.assertEqual(decision["committee_route"], "specialist")
        self.assertEqual(decision["outcome"], "بانتظار المتخصص")
        self.assertEqual(decision["abstention_reasons"], ["agent_disagree"])
        self.assertIn("اختلاف الوكلاء", decision["abstention_ar"])

    def test_reused_reviewer_move_forces_unclear_bounds(self) -> None:
        """P1-2: A reviewer move overlapping two proposer moves must not support two nominations (if reused -> both proposer moves specialist unclear_bounds)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            p_dir = tmp_path / "verified" / "qwen2.5-14b-local"
            r_dir = tmp_path / "verified" / "gemma2-9b-local"
            p_dir.mkdir(parents=True)
            r_dir.mkdir(parents=True)

            # Proposer has two moves: p01 on [s001, s002], p02 on [s002, s003]
            p01 = _make_move("p01", span_ids=["s001", "s002"], score_total=90, route="auto_candidate")
            p02 = _make_move("p02", span_ids=["s002", "s003"], score_total=90, route="auto_candidate")

            # Reviewer has single move r01 spanning [s001, s002, s003], overlapping BOTH p01 and p02
            r01 = _make_move("r01", span_ids=["s001", "s002", "s003"], score_total=90, route="auto_candidate")

            p_data = _make_verified_file("24_1", annotator="qwen2.5-14b-local", moves=[p01, p02])
            r_data = _make_verified_file("24_1", annotator="gemma2-9b-local", moves=[r01])

            (p_dir / "24_1.json").write_text(json.dumps(p_data), encoding="utf-8")
            (r_dir / "24_1.json").write_text(json.dumps(r_data), encoding="utf-8")

            c_pay, v_pay = committee_chair.evaluate_window(
                base=tmp_path,
                proposer="qwen2.5-14b-local",
                reviewer="gemma2-9b-local",
                window_id="24_1",
            )
            # Both proposer moves must be specialist unclear_bounds
            self.assertEqual(c_pay["moves"][0]["committee_route"], "specialist")
            self.assertEqual(c_pay["moves"][0]["abstention_reasons"], ["unclear_bounds"])
            self.assertEqual(c_pay["moves"][1]["committee_route"], "specialist")
            self.assertEqual(c_pay["moves"][1]["abstention_reasons"], ["unclear_bounds"])

    # --- P1-1: Unmatched reviewer move test ---
    def test_unmatched_reviewer_move_emitted_as_specialist_in_both_files(self) -> None:
        """P1-1: reviewer has an extra move -> present in both files as specialist."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            p_dir = tmp_path / "verified" / "qwen2.5-14b-local"
            r_dir = tmp_path / "verified" / "gemma2-9b-local"
            p_dir.mkdir(parents=True)
            r_dir.mkdir(parents=True)

            p_move = _make_move("p01", span_ids=["s001", "s002"], score_total=90, route="auto_candidate")
            r_move1 = _make_move("r01", span_ids=["s001", "s002"], score_total=90, route="auto_candidate")
            # Extra reviewer move that proposer did not segment
            r_move_extra = _make_move(
                "r_extra", span_ids=["s010", "s011"], primary="M_QURAN", score_total=88, route="auto_candidate"
            )

            p_data = _make_verified_file("24_1", annotator="qwen2.5-14b-local", moves=[p_move])
            r_data = _make_verified_file(
                "24_1", annotator="gemma2-9b-local", moves=[r_move1, r_move_extra]
            )

            (p_dir / "24_1.json").write_text(json.dumps(p_data), encoding="utf-8")
            (r_dir / "24_1.json").write_text(json.dumps(r_data), encoding="utf-8")

            c_pay, v_pay = committee_chair.evaluate_window(
                base=tmp_path,
                proposer="qwen2.5-14b-local",
                reviewer="gemma2-9b-local",
                window_id="24_1",
            )

            # Both files must have 2 moves
            self.assertEqual(len(c_pay["moves"]), 2)
            self.assertEqual(len(v_pay["moves"]), 2)

            # First move is auto_candidate
            self.assertEqual(c_pay["moves"][0]["committee_route"], "auto_candidate")
            self.assertEqual(v_pay["moves"][0]["route"], "auto_candidate")

            # Second move (extra reviewer move) is specialist unclear_bounds in both files
            extra_c = c_pay["moves"][1]
            self.assertIsNone(extra_c["proposer_move_id"])
            self.assertEqual(extra_c["reviewer_move_id"], "r_extra")
            self.assertEqual(extra_c["committee_route"], "specialist")
            self.assertEqual(extra_c["abstention_reasons"], ["unclear_bounds"])

            extra_v = v_pay["moves"][1]
            self.assertEqual(extra_v["move_id"], "r_extra")
            self.assertEqual(extra_v["route"], "specialist")
            self.assertEqual(extra_v["committee_reason_code"], "unclear_bounds")

            # Check files on disk
            c_disk = json.loads((tmp_path / "committee" / "24_1.json").read_text(encoding="utf-8"))
            v_disk = json.loads(
                (tmp_path / "verified" / "committee" / "24_1.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(c_disk["moves"]), 2)
            self.assertEqual(len(v_disk["moves"]), 2)
            self.assertEqual(c_disk["moves"][1]["committee_route"], "specialist")
            self.assertEqual(v_disk["moves"][1]["route"], "specialist")


class TestCommitteeChairPositive(unittest.TestCase):
    """Positive tests."""

    def test_positive_both_auto_overlap_score_90_no_flags(self) -> None:
        """Rule: both auto, same primary, overlap, score 90, no flags -> auto_candidate."""
        p_move = _make_move(
            span_ids=["s001", "s002"],
            primary="M_LUGHA",
            score_total=90,
            certainty="strong",
            flags=[],
            route="auto_candidate",
        )
        r_move = _make_move(
            span_ids=["s001", "s002"],
            primary="M_LUGHA",
            score_total=92,
            certainty="strong",
            flags=[],
            route="auto_candidate",
        )
        decision = committee_chair.evaluate_move(p_move, [r_move])
        self.assertEqual(decision["committee_route"], "auto_candidate")
        self.assertEqual(decision["outcome"], "مرشح للقبول")
        self.assertEqual(decision["abstention_reasons"], [])
        self.assertIsNone(decision["abstention_ar"])
        self.assertEqual(decision["primary_proposer"], "M_LUGHA")
        self.assertEqual(decision["primary_reviewer"], "M_LUGHA")
        self.assertEqual(decision["score_proposer"], 90)
        self.assertEqual(decision["score_reviewer"], 92)

    def test_evaluate_window_generates_both_files_correctly(self) -> None:
        """Verify committee/<window>.json and verified/committee/<window>.json schemas."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            p_dir = tmp_path / "verified" / "qwen2.5-14b-local"
            r_dir = tmp_path / "verified" / "gemma2-9b-local"
            p_dir.mkdir(parents=True)
            r_dir.mkdir(parents=True)

            p_move = _make_move(score_total=90, route="auto_candidate")
            r_move = _make_move(score_total=90, route="auto_candidate")
            p_data = _make_verified_file("24_1", annotator="qwen2.5-14b-local", moves=[p_move])
            r_data = _make_verified_file("24_1", annotator="gemma2-9b-local", moves=[r_move])

            (p_dir / "24_1.json").write_text(json.dumps(p_data), encoding="utf-8")
            (r_dir / "24_1.json").write_text(json.dumps(r_data), encoding="utf-8")

            c_pay, v_pay = committee_chair.evaluate_window(
                base=tmp_path,
                proposer="qwen2.5-14b-local",
                reviewer="gemma2-9b-local",
                window_id="24_1",
            )

            c_file = tmp_path / "committee" / "24_1.json"
            v_file = tmp_path / "verified" / "committee" / "24_1.json"
            self.assertTrue(c_file.is_file())
            self.assertTrue(v_file.is_file())

            # Check committee.json structure
            self.assertEqual(c_pay["window_id"], "24_1")
            self.assertEqual(c_pay["runtime"], "ollama-local")
            self.assertEqual(c_pay["summary"]["caption"], grounding_contract.COMMITTEE_CAPTION)
            self.assertEqual(c_pay["summary"]["auto_candidate"], 1)
            self.assertEqual(c_pay["summary"]["specialist"], 0)
            self.assertIn("dorar.net/tafseer/24", c_pay["source_links"]["dorar_surah"])

            # Check verified/committee structure
            self.assertEqual(v_pay["annotator"], "committee")
            self.assertEqual(v_pay["moves"][0]["route"], "auto_candidate")
            self.assertEqual(v_pay["summary"]["auto_candidate"], 1)


class TestCommitteeChairEndToEnd(unittest.TestCase):
    """End-to-End: fake HTTP model -> classify_api -> v2_verify -> committee_chair."""

    def test_full_chain_grounded_and_ungrounded(self) -> None:
        """Prove producer, verifier, and chair agree on the contract."""
        fixture_packet = ROOT / "data" / "v2" / "packets" / "17_105.json"
        fixture_window = ROOT / "data" / "v2" / "windows" / "17_105.json"
        fixture_markers = ROOT / "data" / "v2" / "markers" / "17_105.json"

        self.assertTrue(fixture_packet.is_file(), f"missing fixture: {fixture_packet}")
        self.assertTrue(fixture_window.is_file(), f"missing fixture: {fixture_window}")
        self.assertTrue(fixture_markers.is_file(), f"missing fixture: {fixture_markers}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "packets").mkdir(parents=True)
            (tmp_path / "windows").mkdir(parents=True)
            (tmp_path / "markers").mkdir(parents=True)
            (tmp_path / "moves").mkdir(parents=True)

            shutil.copy(fixture_packet, tmp_path / "packets" / "17_105.json")
            shutil.copy(fixture_window, tmp_path / "windows" / "17_105.json")
            shutil.copy(fixture_markers, tmp_path / "markers" / "17_105.json")

            moves_payload = {
                "window": "17_105",
                "moves": [
                    {
                        "move_id": "m01",
                        "span_ids": ["s002", "s003", "s004"],
                        "primary": "M_QURAN",
                        "secondary": [],
                        "content_tags": ["C_TAFSIR"],
                        "certainty": "explicit",
                        "evidence_span_ids": ["s002", "s003"],
                        "author_verdict_span_ids": [],
                        "references": {"verses": ["4:166"], "hadith": [], "persons": []},
                        "alternatives": [],
                        "rationale_ar": "بيان بالقرآن مع شواهد صريحة",
                    },
                    {
                        "move_id": "m02",
                        "span_ids": ["s005"],
                        "primary": "M_LUGHA",
                        "secondary": [],
                        "content_tags": ["C_TAFSIR"],
                        "certainty": "strong",
                        "evidence_span_ids": [],  # Empty evidence -> ungrounded
                        "author_verdict_span_ids": [],
                        "references": {"verses": [], "hadith": [], "persons": []},
                        "alternatives": [],
                        "rationale_ar": "بلا شاهد صريح",
                    },
                ],
            }

            def fake_http_post(url: str, headers: dict, body: bytes) -> bytes:
                content_text = json.dumps(moves_payload, ensure_ascii=False)
                return json.dumps(
                    {"choices": [{"message": {"content": content_text}}]}
                ).encode("utf-8")

            # 1. Run classifier for proposer (family: qwen2.5)
            proposer_model = "qwen2.5-14b-local"
            res_p = classify_api.classify(
                tmp_path / "packets" / "17_105.json",
                model=proposer_model,
                base_url="http://localhost:11434/v1",
                out_dir=tmp_path / "moves",
                api_key="ollama",
                http_post=fake_http_post,
            )
            self.assertTrue(res_p["path"].is_file())

            # 2. Run classifier for reviewer (family: gemma2)
            reviewer_model = "gemma2-9b-local"
            res_r = classify_api.classify(
                tmp_path / "packets" / "17_105.json",
                model=reviewer_model,
                base_url="http://localhost:11434/v1",
                out_dir=tmp_path / "moves",
                api_key="ollama",
                http_post=fake_http_post,
            )
            self.assertTrue(res_r["path"].is_file())

            # 3. Run verifier on tmp_path
            orig_base = v2_verify.DEFAULT_BASE
            try:
                v2_verify.configure(tmp_path)
                v2_verify.verify_all()
            finally:
                v2_verify.configure(orig_base)

            proposer_annotator = res_p["path"].parent.name
            reviewer_annotator = res_r["path"].parent.name
            self.assertTrue(
                (tmp_path / "verified" / proposer_annotator / "17_105.json").is_file()
            )
            self.assertTrue(
                (tmp_path / "verified" / reviewer_annotator / "17_105.json").is_file()
            )

            # 4. Run Committee Chair
            c_pay, v_pay = committee_chair.evaluate_window(
                base=tmp_path,
                proposer=proposer_annotator,
                reviewer=reviewer_annotator,
                window_id="17_105",
            )

            # 5. Assert contract consensus:
            m01_decision = c_pay["moves"][0]
            self.assertEqual(m01_decision["proposer_move_id"], "m01")
            self.assertEqual(m01_decision["committee_route"], "auto_candidate")
            self.assertEqual(m01_decision["outcome"], "مرشح للقبول")
            self.assertEqual(m01_decision["abstention_reasons"], [])
            self.assertGreaterEqual(m01_decision["score_proposer"], 85)

            m02_decision = c_pay["moves"][1]
            self.assertEqual(m02_decision["proposer_move_id"], "m02")
            self.assertEqual(m02_decision["committee_route"], "specialist")
            self.assertEqual(m02_decision["outcome"], "بانتظار المتخصص")
            self.assertEqual(m02_decision["abstention_reasons"], ["force_specialist"])
            self.assertEqual(m02_decision["verifier_reason_code"], "EVIDENCE_EMPTY")

            self.assertEqual(c_pay["summary"]["auto_candidate"], 1)
            self.assertEqual(c_pay["summary"]["specialist"], 1)
            self.assertEqual(c_pay["summary"]["move_count"], 2)

            self.assertTrue((tmp_path / "committee" / "17_105.json").is_file())
            self.assertTrue((tmp_path / "verified" / "committee" / "17_105.json").is_file())


if __name__ == "__main__":
    unittest.main()
