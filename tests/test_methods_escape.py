"""Negative test: model-supplied joins in methods_template must use escapeHtml."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "methods_template.html"

JOIN_FIELDS = (
    "evidence_span_ids",
    "author_verdict_span_ids",
    "alternatives",
    "flags",
)


def _lines_with_join(field: str) -> list[str]:
    needle = f"{field}"
    out = []
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        if needle in line and ".join(" in line:
            out.append(line)
    return out


class TestMethodsEscape(unittest.TestCase):
    def test_join_fields_use_escape_html(self) -> None:
        self.assertTrue(TEMPLATE.is_file(), f"missing {TEMPLATE}")
        for field in JOIN_FIELDS:
            lines = _lines_with_join(field)
            self.assertTrue(lines, f"expected .join( line mentioning {field}")
            for line in lines:
                self.assertIn(
                    "escapeHtml",
                    line,
                    f"{field} join must be wrapped in escapeHtml:\n{line}",
                )

    def test_escape_html_around_joins_via_node_or_regex(self) -> None:
        """Playwright-free check: node if available, else regex on template source."""
        src = TEMPLATE.read_text(encoding="utf-8")
        # Each sensitive join must appear inside an escapeHtml(...) call on the same statement.
        patterns = [
            r"escapeHtml\(\(h\.evidence_span_ids\s*\|\|\s*\[\]\)\.map\(String\)\.join\(",
            r"escapeHtml\(\(h\.author_verdict_span_ids\s*\|\|\s*\[\]\)\.map\(String\)\.join\(",
            r"escapeHtml\(h\.alternatives\.map\(String\)\.join\(",
            r"escapeHtml\(h\.flags\.map\(String\)\.join\(",
        ]
        for pat in patterns:
            self.assertRegex(src, pat, f"missing escaped join pattern: {pat}")

        node = shutil.which("node")
        if not node:
            return
        # Deterministic runtime check of the page's escapeHtml helper.
        script = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const m = src.match(/function escapeHtml\(s\)\s*\{[\s\S]*?\n  \}/);
if (!m) { console.error("escapeHtml not found"); process.exit(2); }
eval(m[0]);
const payload = ['</p><img src=x onerror=alert(1)>', 'a&b'];
const out = escapeHtml(payload.map(String).join(", "));
if (out.includes("<img") || out.includes("</p>") || !out.includes("&amp;")) {
  console.error("escapeHtml failed:", out);
  process.exit(1);
}
if (!out.includes("&lt;") || !out.includes("&gt;")) {
  console.error("escapeHtml missing lt/gt:", out);
  process.exit(1);
}
console.log("ESCAPE_OK");
"""
        proc = subprocess.run(
            [node, "-e", script, str(TEMPLATE)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("ESCAPE_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
