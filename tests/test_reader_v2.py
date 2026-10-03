"""Static checks and gate tests for UI v2 (web/reader.html and src/fahras_v2_template.html)."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import build_fahras  # noqa: E402


class TestReaderV2(unittest.TestCase):
    def setUp(self) -> None:
        self.template_path = ROOT / "src" / "fahras_v2_template.html"
        self.reader_path = ROOT / "web" / "reader.html"
        self.fahras_template = ROOT / "src" / "fahras_template.html"
        self.fahras_html = ROOT / "web" / "fahras.html"

    def test_files_exist_and_non_empty(self) -> None:
        self.assertTrue(self.template_path.is_file(), "src/fahras_v2_template.html missing")
        self.assertTrue(self.reader_path.is_file(), "web/reader.html missing")
        self.assertGreater(self.template_path.stat().st_size, 1000)
        self.assertGreater(self.reader_path.stat().st_size, 500000)

    def test_reader_html_passes_build_fahras_check_html(self) -> None:
        html = self.reader_path.read_bytes().decode("utf-8")
        # Must not raise SystemExit
        build_fahras.check_html(html)

    def test_no_forbidden_markup(self) -> None:
        html = self.reader_path.read_bytes().decode("utf-8").lower()
        for token in ("<!doctype", "<html", "</html", "<head>", "<head ", "</head", "<body", "</body"):
            self.assertNotIn(token, html, f"forbidden markup token: {token}")

    def test_only_allowed_external_urls(self) -> None:
        html = self.reader_path.read_bytes().decode("utf-8")
        urls = re.findall(r"(?:href|src)\s*=\s*[\"'](https?://[^\"']+)", html, flags=re.I)
        urls += re.findall(r"url\(\s*[\"']?(https?://[^)\"']+)", html, flags=re.I)
        allowed = ("fonts.googleapis.com", "tafsir.net", "dorar.net", "quran.com")
        for u in urls:
            self.assertTrue(
                any(a in u for a in allowed),
                f"unallowed external URL: {u}",
            )

    def test_no_wide_side_borders(self) -> None:
        html = self.reader_path.read_bytes().decode("utf-8")
        stripe = re.findall(
            r"border-(?:inline-start|inline-end|left|right)\s*:\s*([0-9.]+)px",
            html,
            flags=re.I,
        )
        wide = [x for x in stripe if float(x) > 1]
        self.assertEqual(wide, [], f"side-stripe borders >1px found: {wide}")

    def test_reader_mode_elements_present(self) -> None:
        html = self.reader_path.read_bytes().decode("utf-8")
        self.assertIn('id="reader-view"', html)
        self.assertIn('id="reader-ayah-text"', html)
        self.assertIn('id="reader-chips-bar"', html)
        self.assertIn('id="chip-none"', html)
        self.assertIn('id="reading-article"', html)
        self.assertIn('id="evidence-card"', html)
        self.assertIn('id="dist-bar"', html)
        self.assertIn('id="dist-legend"', html)
        self.assertIn('id="reader-toc"', html)
        self.assertIn('id="toggle-footnotes"', html)
        self.assertIn('id="btn-font-dec"', html)
        self.assertIn('id="btn-font-inc"', html)

    def test_review_mode_elements_present(self) -> None:
        html = self.reader_path.read_bytes().decode("utf-8")
        self.assertIn('id="review-view"', html)
        self.assertIn('id="review-queue-panel"', html)
        self.assertIn('id="tab-pending"', html)
        self.assertIn('id="tab-candidate"', html)
        self.assertIn('id="tab-done"', html)
        self.assertIn('id="review-paper"', html)
        self.assertIn('id="review-cmp-badge"', html)
        self.assertIn('id="dec-score-total"', html)
        self.assertIn('id="review-note"', html)
        self.assertIn('id="act-approve"', html)
        self.assertIn('id="act-edit"', html)
        self.assertIn('id="act-reject"', html)
        self.assertIn('id="btn-export-decisions"', html)
        self.assertIn('id="export-modal"', html)

    def test_data_payload_matches_fahras_html(self) -> None:
        reader_html = self.reader_path.read_bytes().decode("utf-8")
        fahras_html = self.fahras_html.read_bytes().decode("utf-8")

        m1 = re.search(r'<script type="application/json" id="methods-data">([^<]+)</script>', reader_html)
        m2 = re.search(r'<script type="application/json" id="methods-data">([^<]+)</script>', fahras_html)
        self.assertIsNotNone(m1, "methods-data missing in reader.html")
        self.assertIsNotNone(m2, "methods-data missing in fahras.html")

        d1 = json.loads(m1.group(1))
        d2 = json.loads(m2.group(1))
        self.assertEqual(d1["data_version"], d2["data_version"])
        self.assertEqual(d1["tafsir_order"], d2["tafsir_order"])
        self.assertEqual(d1["window_order"], d2["window_order"])

    def test_fahras_template_has_link_to_reader(self) -> None:
        t = self.fahras_template.read_bytes().decode("utf-8")
        self.assertIn('href="reader.html"', t)
        self.assertIn("جرّب الواجهة الجديدة", t)

    def test_delta_review_fixes(self) -> None:
        template = self.template_path.read_bytes().decode("utf-8")

        # 1. Export shape
        self.assertIn("function buildExportRecord(h)", template)
        self.assertIn("function exportApprovedRecords()", template)
        self.assertIn("text_fidelity", template)
        self.assertIn("ai_proposal", template)

        # 2. Gate approval on fidelity
        self.assertIn("function canApproveMove(move)", template)
        self.assertIn("function verifyBoundaryFidelity(", template)
        self.assertIn("showFidelityError", template)

        # 3. Dynamic reconstruction check & no unconditional quran.com claim in badge
        self.assertIn("updateReviewReconstructionBadge", template)
        self.assertIn("collectSourceRunText", template)
        badge_html = template.split('id="review-cmp-badge"')[1].split("</span>")[0]
        self.assertNotIn("quran.com", badge_html)

        # 4. Boundary buttons wired
        for btn in ("btn-adj-before", "btn-adj-shrink-start", "btn-adj-after", "btn-adj-shrink-end"):
            self.assertIn(btn, template)
        self.assertIn("adjustBoundary", template)

        # 5. Missing score defaults to dash
        self.assertIn('scoreEl.textContent = "—"', template)
        self.assertNotIn("scoreVal = 100", template)

        # 6. Zero innerHTML across template
        self.assertNotIn(".innerHTML", template)

        # 7. Mobile review queue collapsed
        self.assertIn("@media (max-width: 992px)", template)
        self.assertIn(".queue-panel.is-collapsed", template)

        # 8. No trim() on source text
        self.assertNotIn("slice.trim()", template)
        self.assertNotIn("text.trim()", template)

        # 9. Method tint and underline, outline only on is-selected
        self.assertIn(".hl.is-selected", template)

        # 10. Evidence card anchored within reader col
        self.assertIn("evidence-card", template)
        self.assertIn("colRect", template)

    def test_delta_2_codex_fixes(self) -> None:
        template = self.template_path.read_bytes().decode("utf-8")

        # 1. Compare gate
        self.assertIn("comparedKey", template)
        self.assertIn("function compareKey(h)", template)
        self.assertIn("state.comparedKey !== k", template)
        self.assertIn("runCompareWithSource", template)

        # 2. Boundary gate compares rendered text against pinned source
        self.assertIn("getRenderedMoveText", template)
        self.assertIn("verifyBoundaryFidelity(move.start, move.end, rendered)", template)

        # 3. Export approved only; 0 approved exports nothing
        self.assertNotIn("approved = [buildExportRecord(getSelectedMove())]", template)
        self.assertIn("لا توجد وسوم معتمدة بعد", template)

        # 4. Reader banner conditional on reconstruction check
        self.assertIn("updateReaderReconstructionBanner", template)
        self.assertIn("checkReconstructionFidelity", template)
        self.assertIn("is-mismatch", template)

        # 5. Remove static «/ ١٠٠» placeholder
        self.assertNotIn('>/ ١٠٠<', template)
        self.assertNotIn('> / ١٠٠<', template)

        # 6. Popover clamped inside reader-col
        self.assertIn("Math.max(minLeft, Math.min(maxLeft,", template)

    def test_delta_3_codex_fixes(self) -> None:
        template = self.template_path.read_bytes().decode("utf-8")

        # 1. No static scale in template; scale dynamically set with VERIFIER_SCORE_MAX
        self.assertNotIn(">/ ١٠٠<", template)
        self.assertNotIn("> / ١٠٠<", template)
        self.assertIn("VERIFIER_SCORE_MAX = 100", template)
        self.assertIn('scaleEl.textContent = hasScore ? (" / " + toArabicDigits(VERIFIER_SCORE_MAX)) : ""', template)

        # 2. Initial review stats markup has no hardcoded status text
        header_stats_block = template.split('id="header-review-stats"')[1].split('</div>')[0]
        self.assertNotIn("معتمد", header_stats_block)
        self.assertNotIn("مرفوض", header_stats_block)

        # 3. Replay checks data_version and source fidelity, sets needs_recheck on failure
        self.assertIn("needs_recheck", template)
        self.assertIn("Boolean(e.data_version && DATA.data_version && e.data_version === DATA.data_version)", template)
        self.assertIn("قرار سابق يحتاج إعادة تحقق", template)

        # 4. Approved export wrapped as EXACTLY { data_version, records }
        self.assertIn("function getApprovedExportPayload()", template)
        payload_fn = template.split("function getApprovedExportPayload()")[1].split("}")[0]
        self.assertIn("data_version: DATA.data_version || \"\"", payload_fn)
        self.assertIn("records: records", payload_fn)
        self.assertNotIn("annotations", payload_fn)


if __name__ == "__main__":
    unittest.main()


