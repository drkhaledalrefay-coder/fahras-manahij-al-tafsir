"""Inline the index and reconciliation JSON into the single-file demo app.

Reads web/index_data.json and web/reconcile_data.json (built by the existing
scripts) and writes web/app.html from src/app_template.html. Does not analyze
text and does not touch data/.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_MARKER = "__INDEX_DATA_JSON__"
RECON_MARKER = "__RECONCILE_JSON__"

# Fields the reconciliation screen actually reads. Everything else (word index,
# per-diff norms, span id lists, precomputed gap tables, excel bookkeeping)
# is dropped so the published file stays small.
DIFF_KEYS = (
    "kind",
    "annotation_words",
    "source_words",
    "source_start",
    "source_end",
    "annotation_start",
    "annotation_end",
    "pair",
)


def embed(payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def trim_reconcile(payload: dict) -> dict:
    words = [
        {
            "start": word["start"],
            "end": word["end"],
            "norm": word["norm"],
            "layer": word["layer"],
        }
        for word in payload["words"]
    ]
    sets = []
    for group in payload["sets"]:
        units = []
        for unit in group["units"]:
            fragments = []
            for fragment in unit.get("fragments") or []:
                fragments.append(
                    {
                        "words": [
                            {
                                "start": word["start"],
                                "end": word["end"],
                                "norm": word["norm"],
                            }
                            for word in fragment.get("words") or []
                        ]
                    }
                )
            units.append(
                {
                    "unit_id": unit["unit_id"],
                    "text": unit["text"],
                    "tags": unit.get("tags") or {"source": [], "content": []},
                    "note_ar": unit.get("note_ar") or "",
                    "note_label_ar": unit.get("note_label_ar") or "",
                    "confidence": unit.get("confidence"),
                    "color": unit["color"],
                    "reasons": list(unit.get("reasons") or []),
                    "summary_ar": unit.get("summary_ar") or "",
                    "diacritics_or_punctuation_differ": bool(
                        unit.get("diacritics_or_punctuation_differ")
                    ),
                    "differences": [
                        {key: diff[key] for key in DIFF_KEYS if key in diff}
                        for diff in unit.get("differences") or []
                    ],
                    "location": {
                        "start": unit["location"]["start"],
                        "end": unit["location"]["end"],
                    },
                    "fragments": fragments,
                    "source_runs": unit.get("source_runs") or [],
                    "ann_runs": unit.get("ann_runs") or [],
                    "leading_elision": bool(unit.get("leading_elision")),
                    "trailing_elision": bool(unit.get("trailing_elision")),
                }
            )
        sets.append(
            {"id": group["id"], "label_ar": group["label_ar"], "units": units}
        )
    source = payload["source"]
    return {
        "source": {
            "file": source["file"],
            "sha256": source["sha256"],
            "window_start": source["window_start"],
            "window_end": source["window_end"],
            "next_char": source["next_char"],
            "text": source["text"],
        },
        "words": words,
        "layers": payload["layers"],
        "sets": sets,
    }


def _statuses(node: object, found: list[str]) -> None:
    if isinstance(node, dict):
        status = node.get("status")
        if isinstance(status, str):
            found.append(status)
        for value in node.values():
            _statuses(value, found)
    elif isinstance(node, list):
        for value in node:
            _statuses(value, found)


def check_html(html: str, index_data: dict, recon_data: dict) -> None:
    if not html.startswith("<meta charset=\"utf-8\">"):
        raise SystemExit("app.html must start with the charset meta")
    if "\r" in html:
        raise SystemExit("app.html must use LF newlines")
    lowered = html.lower()
    for token in ("<!doctype", "<html", "<head", "<body", "</head", "</body", "</html"):
        if token in lowered:
            raise SystemExit(f"forbidden markup: {token}")
    urls = re.findall(r"(?:href|src)\s*=\s*[\"'](https?://[^\"']+)", html, flags=re.I)
    urls += re.findall(r"url\(\s*[\"']?(https?://[^)\"']+)", html, flags=re.I)
    bad = [url for url in urls if "fonts.googleapis.com" not in url]
    if bad:
        raise SystemExit("unexpected external URL: " + ", ".join(bad))
    if "fonts.googleapis.com" not in html:
        raise SystemExit("missing Google Fonts stylesheet")
    if html.count(INDEX_MARKER) or html.count(RECON_MARKER):
        raise SystemExit("JSON markers were not replaced")
    if "تمت المطابقة" in html:
        raise SystemExit("forbidden phrase: تمت المطابقة")
    for phrase in (
        "اختلاف طبعات أو إملاء",
        "يحسمها المتخصص",
        "اعرض الفروق",
        "لماذا هذه الوسوم؟",
        "مقارنة بالنص الأصلي",
        "#fahras",
        "#mutabaqa",
        "#tajruba",
    ):
        if phrase not in html:
            raise SystemExit(f"missing required phrase: {phrase}")

    blocks = re.findall(
        r'<script type="application/json" id="(index-data|reconcile-data)">(.*?)</script>',
        html,
    )
    if [item[0] for item in blocks] != ["index-data", "reconcile-data"]:
        raise SystemExit("expected index-data then reconcile-data JSON blocks")
    parsed = []
    for name, raw in blocks:
        try:
            parsed.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{name} JSON did not parse: {exc}") from exc
    if parsed[0]["summary"]["total_spans"] != index_data["summary"]["total_spans"]:
        raise SystemExit("inlined index JSON does not match the source file")
    if parsed[1]["source"]["sha256"] != recon_data["source"]["sha256"]:
        raise SystemExit("inlined reconcile JSON does not match the trimmed payload")
    statuses: list[str] = []
    _statuses(parsed[0], statuses)
    _statuses(parsed[1], statuses)
    if any(status == "approved" for status in statuses):
        raise SystemExit("data contains status approved")
    if "approved" in json.dumps(parsed[0], ensure_ascii=False):
        raise SystemExit("index JSON contains the string approved")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    index_path = ROOT / "web" / "index_data.json"
    recon_path = ROOT / "web" / "reconcile_data.json"
    template_path = ROOT / "src" / "app_template.html"
    if not index_path.is_file() or not recon_path.is_file():
        raise SystemExit("missing web JSON; run build_index.py and build_reconcile.py first")

    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    recon_raw = json.loads(recon_path.read_text(encoding="utf-8"))
    recon_data = trim_reconcile(recon_raw)
    template = template_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if template.count(INDEX_MARKER) != 1 or template.count(RECON_MARKER) != 1:
        raise SystemExit("template markers must appear exactly once each")

    html = template.replace(INDEX_MARKER, embed(index_data)).replace(
        RECON_MARKER, embed(recon_data)
    )
    check_html(html, index_data, recon_data)

    out = ROOT / "web" / "app.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    raw_bytes = recon_path.stat().st_size
    trimmed = len(embed(recon_data).encode("utf-8"))
    html_bytes = out.stat().st_size
    print(f"Wrote {out.relative_to(ROOT)}")
    print(f"html_bytes={html_bytes}")
    print(f"reconcile_raw_bytes={raw_bytes} reconcile_inlined_bytes={trimmed}")
    print(f"index_units={sum(len(a['units']) for a in index_data['ayat'])}")
    print(
        "reconcile_units="
        + ",".join(f"{group['id']}:{len(group['units'])}" for group in recon_data["sets"])
    )
    print("CHECK ok")
    if html_bytes >= 800 * 1024:
        raise SystemExit("app.html is over 800 KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
