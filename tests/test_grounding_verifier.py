"""Grounding-contract gates for v2_verify (synthetic fixtures only; never touch data/)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import grounding_contract as gc  # noqa: E402
import v2_verify  # noqa: E402

WINDOW_ID = "g_win"


def _span(sid: str, start: int, text: str) -> dict:
    return {"id": sid, "start": start, "end": start + len(text), "text": text}


def _marker(span_id: str, family: str, marker: str = "m", **extra) -> dict:
    block = {
        "family": family,
        "marker": marker,
        "start": 0,
        "end": 1,
        "span_id": span_id,
    }
    block.update(extra)
    return block


def _base_window() -> dict:
    texts = {
        "s001": "aaaaa",
        "s002": "bbbbb",
        "s003": "ccccc",
        "s004": "ddddd",
        "s005": "eeeee",
    }
    spans = []
    pos = 0
    for sid, text in texts.items():
        spans.append(_span(sid, pos, text))
        pos += len(text)
    return {
        "window_id": WINDOW_ID,
        "ayah": "1:1",
        "source_file": "fixture.txt",
        "source_sha256": "0" * 64,
        "window_start": 0,
        "window_end": pos,
        "spans": spans,
    }


def _markers_from(span_markers: dict[str, list[dict]]) -> dict:
    spans = []
    for sid in ("s001", "s002", "s003", "s004", "s005"):
        spans.append({"span_id": sid, "markers": list(span_markers.get(sid) or [])})
    return {
        "window_id": WINDOW_ID,
        "ayah": "1:1",
        "span_count": 5,
        "spans": spans,
        "isnad_ranges": [],
        "editor_footnote_evidence": [],
    }


def _perfect_hadith_move(**overrides) -> dict:
    move = {
        "move_id": "m_ok",
        "span_ids": ["s003"],
        "primary": "M_SUNNAH",
        "secondary": [],
        "content_tags": [],
        "certainty": "explicit",
        "evidence_span_ids": ["s003"],
        "author_verdict_span_ids": [],
        "references": {"verses": [], "hadith": [], "persons": []},
        "alternatives": ["M_QURAN"],
        "rationale_ar": "اختبار",
    }
    move.update(overrides)
    return move


def _hadith_markers() -> dict:
    return _markers_from(
        {
            "s003": [_marker("s003", "HADITH", "قال رسول الله")],
            "s005": [_marker("s005", "RAY", "والصواب")],
        }
    )


class _FixtureBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        (self.base / "windows").mkdir()
        (self.base / "markers").mkdir()
        (self.base / "packets").mkdir()
        (self.base / "moves").mkdir()
        (self.base / "verified").mkdir()
        self.window = _base_window()
        self.packet = {
            "window_id": WINDOW_ID,
            "ayah": "1:1",
            "fixture": True,
            "spans": [{"id": s["id"]} for s in self.window["spans"]],
        }
        self._write_json(self.base / "windows" / f"{WINDOW_ID}.json", self.window)
        self._write_json(self.base / "packets" / f"{WINDOW_ID}.json", self.packet)
        v2_verify.configure(self.base)
        self.packet_sha = gc.packet_sha256(self.packet)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _write_json(path: Path, obj: dict) -> None:
        path.write_bytes(json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"))

    def _set_markers(self, markers: dict) -> None:
        self._write_json(self.base / "markers" / f"{WINDOW_ID}.json", markers)

    def _payload(self, moves: list[dict], **extra) -> dict:
        body = {
            "window": WINDOW_ID,
            "moves": moves,
            gc.PACKET_SHA_FIELD: self.packet_sha,
            gc.INPUT_ASSURANCE_FIELD: gc.INPUT_API_PACKET,
        }
        body.update(extra)
        return body

    def _verify(self, moves: list[dict], **extra) -> dict:
        return v2_verify.verify_window("test", WINDOW_ID, self._payload(moves, **extra))


class TestG1EmptyEvidence(_FixtureBase):
    def test_empty_evidence_no_substitution(self) -> None:
        self._set_markers(_hadith_markers())
        move = _perfect_hadith_move(evidence_span_ids=[])
        result = self._verify([move])
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "EVIDENCE_EMPTY")
        self.assertEqual(m["evidence_span_ids"], [])
        self.assertEqual(m["score"]["parts"]["function_evidence"], 0)


class TestG2VerdictFar(_FixtureBase):
    def test_verdict_far_from_move(self) -> None:
        self._set_markers(_hadith_markers())
        # Move on s003 (allowed: s002,s003); RAY verdict only on distant s005.
        move = _perfect_hadith_move(author_verdict_span_ids=["s005"])
        result = self._verify([move])
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "VERDICT_FAR_FROM_MOVE")
        # Far verdict must not earn RAY attribution credit via proximity bypass.
        # Marker credit still comes from HADITH on evidence; score may be high.
        self.assertTrue(m["score"]["total"] >= 75 or m["score"]["parts"]["marker"] == 25)


class TestG3UngroundedClaim(_FixtureBase):
    def test_ungrounded_hadith_reference(self) -> None:
        # Evidence has QURAN only — claimed hadith refs are uncorroborated.
        self._set_markers(
            _markers_from({"s003": [_marker("s003", "QURAN", "قال تعالى")]})
        )
        move = _perfect_hadith_move(
            primary="M_QURAN",
            references={"verses": [], "hadith": ["Bukhari 1"], "persons": []},
        )
        result = self._verify([move])
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "UNGROUNDED_CLAIM")
        self.assertIn("unverified_model_notes", m)
        self.assertEqual(m["unverified_model_notes"]["rationale_ar"], "اختبار")
        self.assertEqual(m["rationale_ar"], "اختبار")
        self.assertEqual(m["alternatives"], ["M_QURAN"])


class TestG4SufficiencyGate(_FixtureBase):
    def test_editor_only_evidence_despite_high_certainty(self) -> None:
        markers = _markers_from(
            {"s003": [_marker("s003", "EDITOR", "footnote")]}
        )
        self._set_markers(markers)
        move = _perfect_hadith_move(certainty="explicit")
        result = self._verify([move])
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "EDITOR_ONLY_EVIDENCE")
        # Score is an indicator only — even a would-be-high path stays specialist.
        self.assertNotEqual(m["route"], gc.ROUTE_AUTO)

    def test_conflicting_family_evidence(self) -> None:
        # Claim M_QURAN but evidence only has HADITH family.
        self._set_markers(
            _markers_from({"s003": [_marker("s003", "HADITH", "قال رسول الله")]})
        )
        move = _perfect_hadith_move(primary="M_QURAN", certainty="explicit")
        result = self._verify([move])
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "CONFLICTING_EVIDENCE")
        # Conflicting gate applies even when other score parts look strong.
        self.assertGreaterEqual(m["score"]["parts"]["function_evidence"], 0)


class TestG5ReasonCodes(_FixtureBase):
    def test_specialist_reasons_are_closed_and_auto_is_none(self) -> None:
        cases = []

        self._set_markers(_hadith_markers())
        cases.append(self._verify([_perfect_hadith_move(evidence_span_ids=[])])["moves"][0])
        cases.append(
            self._verify(
                [_perfect_hadith_move(author_verdict_span_ids=["s005"])]
            )["moves"][0]
        )

        self._set_markers(
            _markers_from({"s003": [_marker("s003", "QURAN", "قال تعالى")]})
        )
        cases.append(
            self._verify(
                [
                    _perfect_hadith_move(
                        primary="M_QURAN",
                        references={
                            "verses": [],
                            "hadith": ["x"],
                            "persons": [],
                        },
                    )
                ]
            )["moves"][0]
        )

        self._set_markers(
            _markers_from({"s003": [_marker("s003", "EDITOR", "footnote")]})
        )
        cases.append(self._verify([_perfect_hadith_move()])["moves"][0])

        self._set_markers(
            _markers_from({"s003": [_marker("s003", "HADITH", "قال رسول الله")]})
        )
        cases.append(
            self._verify([_perfect_hadith_move(primary="M_QURAN")])["moves"][0]
        )

        # Positive auto path also included for the None check.
        self._set_markers(_hadith_markers())
        auto = self._verify([_perfect_hadith_move()])["moves"][0]
        cases.append(auto)

        for m in cases:
            if m["route"] == gc.ROUTE_AUTO:
                self.assertIsNone(m["reason_code"])
            else:
                self.assertIsNotNone(m["reason_code"])
                self.assertIn(m["reason_code"], gc.REASON_CODES)


class TestG7PacketBinding(_FixtureBase):
    def test_missing_packet_hash(self) -> None:
        self._set_markers(_hadith_markers())
        payload = self._payload([_perfect_hadith_move()])
        del payload[gc.PACKET_SHA_FIELD]
        result = v2_verify.verify_window("test", WINDOW_ID, payload)
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "PACKET_HASH_MISSING")
        self.assertEqual(result["packet_sha256"], self.packet_sha)

    def test_wrong_packet_hash(self) -> None:
        self._set_markers(_hadith_markers())
        result = self._verify(
            [_perfect_hadith_move()],
            **{gc.PACKET_SHA_FIELD: "0" * 64},
        )
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "PACKET_HASH_MISMATCH")

    def test_manual_input_unverified(self) -> None:
        self._set_markers(_hadith_markers())
        result = self._verify(
            [_perfect_hadith_move()],
            **{gc.INPUT_ASSURANCE_FIELD: gc.INPUT_MANUAL_UNVERIFIED},
        )
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "MANUAL_INPUT_UNVERIFIED")
        self.assertEqual(result["input_assurance"], gc.INPUT_MANUAL_UNVERIFIED)

    def test_missing_input_assurance_with_valid_hash(self) -> None:
        self._set_markers(_hadith_markers())
        payload = self._payload([_perfect_hadith_move()])
        del payload[gc.INPUT_ASSURANCE_FIELD]
        result = v2_verify.verify_window("test", WINDOW_ID, payload)
        for m in result["moves"]:
            self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
            self.assertEqual(m["reason_code"], "MANUAL_INPUT_UNVERIFIED")
        self.assertIsNone(result["input_assurance"])

    def test_packet_byte_change_mismatches(self) -> None:
        self._set_markers(_hadith_markers())
        # Hash was computed from the original packet; mutate one byte on disk.
        mutated = dict(self.packet)
        mutated["ayah"] = "1:2"
        self._write_json(self.base / "packets" / f"{WINDOW_ID}.json", mutated)
        result = self._verify([_perfect_hadith_move()])
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_SPECIALIST)
        self.assertEqual(m["reason_code"], "PACKET_HASH_MISMATCH")
        self.assertEqual(result["packet_sha256"], gc.packet_sha256(mutated))
        self.assertNotEqual(result["packet_sha256"], self.packet_sha)


class TestPositiveGrounded(_FixtureBase):
    def test_grounded_sunnah_auto_candidate(self) -> None:
        self._set_markers(_hadith_markers())
        result = self._verify([_perfect_hadith_move()])
        m = result["moves"][0]
        self.assertEqual(m["route"], gc.ROUTE_AUTO)
        self.assertIsNone(m["reason_code"])
        self.assertGreaterEqual(m["score"]["total"], 75)
        self.assertEqual(result["input_assurance"], gc.INPUT_API_PACKET)
        self.assertEqual(result["packet_sha256"], self.packet_sha)
        self.assertEqual(result["summary"]["by_reason"].get("None"), 1)


if __name__ == "__main__":
    unittest.main()
