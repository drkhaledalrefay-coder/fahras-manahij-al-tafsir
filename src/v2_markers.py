"""Deterministic methodology marker detection per author span (original offsets)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from normalize import remove_tashkeel  # noqa: E402

DEFAULT_BASE = "data/v2"
DEFAULT_TAFSIR_NAME = "ابن كثير"

WINDOWS_DIR = ROOT / "data" / "v2" / "windows"
OUT_DIR = ROOT / "data" / "v2" / "markers"

# Layout markup must never become editor-footnote evidence.
_LAYOUT_SKIP = frozenset({"layout", "<br>", "<br/>", "<br />"})

_TASHKEEL_RE = re.compile("[\u064b-\u065f\u0670]")

# ---------------------------------------------------------------------------
# Phrase / regex catalogues (documented in method/markers_v2.md)
# Matching runs on tashkeel-stripped text; offsets map back to original.
# ---------------------------------------------------------------------------

QURAN_PHRASES = [
    "كما قال تعالى",
    "وقال تعالى",
    "قوله تعالى",
    "قال تعالى",
    "وقوله تعالى",
    "لقوله تعالى",
]

HADITH_PHRASES = [
    "قال رسول الله",
    "أن النبي",
    "ان النبي",
    "أن رسول الله",
    "ان رسول الله",
    "رواه",
    "أخرجه",
    "في الصحيح",
    "حدثنا",
    "أخبرنا",
    "اخبرنا",
    "صلى الله عليه وسلم",
]

SAHABA_NAMES = [
    "ابن عباس",
    "ابن مسعود",
    "أبي بن كعب",
    "ابي بن كعب",
    "أبو هريرة",
    "ابو هريرة",
    "أبو بكر",
    "ابو بكر",
    "أبو ذر",
    "ابو ذر",
    "أبو سعيد",
    "ابو سعيد",
    "أبو موسى الأشعري",
    "ابو موسى الاشعري",
    "عبد الله بن عمرو",
    "أبو أمامة",
    "ابو امامة",
    "ابن عمر",
    "عائشة",
    "عثمان",
    "معاذ",
    "جابر",
    "أنس",
    "انس",
    # shorter names last to avoid over-matching inside longer forms when scanning left→right
    "علي",
    "عمر",
]

TABIIN_NAMES = [
    "سعيد بن جبير",
    "أبو العالية",
    "ابو العالية",
    "كعب الأحبار",
    "كعب الاحبار",
    "ابن زيد",
    "الحسن البصري",
    "أبو مالك",
    "ابو مالك",
    "زيد بن أسلم",
    "زيد بن اسلم",
    "ابن جريج",
    "محمد بن كعب القرظي",
    "إبراهيم النخعي",
    "ابراهيم النخعي",
    "الشعبي",
    "علي بن أبي طلحة",
    "علي بن ابي طلحة",
    "مجاهد",
    "قتادة",
    "الحسن",
    "عكرمة",
    "الضحاك",
    "السدي",
    "عطاء",
    "الربيع",
]

ISRAILIYYAT_PHRASES = [
    "كعب الأحبار",
    "كعب الاحبار",
    "وهب بن منبه",
    "أهل الكتاب",
    "اهل الكتاب",
    "بني إسرائيل",
    "بني اسرائيل",
    "الإسرائيليات",
    "الاسرائيليات",
    "من كتبهم",
    "كتب بني إسرائيل",
    "كتب بني اسرائيل",
]

LUGHA_PHRASES = [
    "أي:",
    "اي:",
    "معناه",
    "يقال",
    "والعرب تقول",
    "في اللغة",
    "قال الشاعر",
    "وأنشد",
    "وانشد",
    "كقوله",
    "كقول",
]

QIRAAT_PHRASES = [
    "وفي قراءة",
    "قراءة",
    "قرأه",
    "قرأ",
]

NUZUL_PHRASES = [
    "نزلت في",
    "سبب نزول",
    "فأنزل الله",
    "فانزل الله",
    "فنزلت",
    "فأنزل",
]

SIRA_PHRASES = [
    "يوم بدر",
    "يوم أحد",
    "يوم احد",
    "غزوة",
    "خرج رسول الله",
]

RAY_PHRASES = [
    "والأظهر",
    "والاظهر",
    "والصحيح",
    "والظاهر",
    "والراجح",
    "وهذا أولى",
    "وهذا اولى",
    "والمعنى",
    "والأقرب",
    "والاقرب",
    "وأقرب",
    "واقرب",
    "قلت",
    "والله أعلم",
    "والله اعلم",
    "وهذا إسناد",
    "وهذا اسناد",
    "غريب",
    "فيه نظر",
]

GRADING_WORDS = ["صحيح", "حسن", "ضعيف", "سنده", "إسناده", "اسناده"]

# Quran quotation delimiters (original text).
_QURAN_CURLY = re.compile(r"\{[^{}]+\}")
_QURAN_ORNAMENT = re.compile("\ufd3f[^\ufd3e]+\ufd3e")  # ﴿…﴾

# Isnad chain patterns on stripped text.
_ISNAD_AN = re.compile(
    r"عن\s+\S+(?:\s+\S+){0,3}(?:\s+عن\s+\S+(?:\s+\S+){0,3}){1,6}"
)
_ISNAD_HADDATHANA = re.compile(
    r"(?:حدثنا|أخبرنا|اخبرنا)\s+\S+(?:\s+\S+){0,2}"
    r"(?:\s+(?:حدثنا|أخبرنا|اخبرنا)\s+\S+(?:\s+\S+){0,2}){1,5}"
)

# Salawat symbol
_SALAWAT = "\ufdfa"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _resolve_base(base: str | Path) -> Path:
    p = Path(base)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def configure(base: str | Path = DEFAULT_BASE) -> Path:
    """Point windows/markers dirs at <base>. Returns resolved base path."""
    global WINDOWS_DIR, OUT_DIR
    base_path = _resolve_base(base)
    WINDOWS_DIR = base_path / "windows"
    OUT_DIR = base_path / "markers"
    return base_path


def _normalize_apparatus(apparatus: list[dict]) -> list[dict]:
    """Map multi {kind,subtype} → v2 {layer}; drop layout markup (<br>)."""
    out: list[dict] = []
    for a in apparatus:
        if a.get("kind") == "layout":
            continue
        layer = a.get("layer")
        if layer is None:
            layer = a.get("subtype")
        text = a.get("text") or ""
        if not layer or layer in _LAYOUT_SKIP or text.strip() in _LAYOUT_SKIP:
            continue
        item = dict(a)
        item["layer"] = layer
        out.append(item)
    return out


def _strip_map(text: str) -> tuple[str, list[int]]:
    """Return tashkeel-stripped text and map stripped_index → original_index."""
    out_chars: list[str] = []
    mapping: list[int] = []
    for i, ch in enumerate(text):
        if _TASHKEEL_RE.match(ch):
            continue
        out_chars.append(ch)
        mapping.append(i)
    return "".join(out_chars), mapping


def _map_span(mapping: list[int], a: int, b: int, orig_len: int) -> tuple[int, int]:
    """Map [a,b) in stripped space to original [start,end)."""
    if not mapping or a >= len(mapping):
        return 0, 0
    start = mapping[a]
    if b <= 0:
        end = start
    elif b >= len(mapping):
        end = orig_len
    else:
        end = mapping[b - 1] + 1
    return start, end


def _find_phrases(
    stripped: str, mapping: list[int], orig_len: int, phrases: list[str], family: str
) -> list[dict]:
    hits: list[dict] = []
    for phrase in phrases:
        start = 0
        while True:
            idx = stripped.find(phrase, start)
            if idx < 0:
                break
            oa, ob = _map_span(mapping, idx, idx + len(phrase), orig_len)
            hits.append(
                {
                    "family": family,
                    "marker": phrase,
                    "start": oa,
                    "end": ob,
                }
            )
            start = idx + 1
    return hits


def _attribution_hits(
    stripped: str,
    mapping: list[int],
    orig_len: int,
) -> list[dict]:
    """Classify named sources as speakers or chain narrators."""
    hits: list[dict] = []
    families = {name: "TABIIN" for name in TABIIN_NAMES}
    families.update({name: "SAHABA" for name in SAHABA_NAMES})
    # Longest alternative wins (الحسن البصري before الحسن, علي بن أبي طلحة before علي).
    names = "|".join(re.escape(n) for n in sorted(families, key=len, reverse=True))
    name_rx = re.compile(rf"(?<!\w)(?:{names})(?!\w)")
    chain_ranges = [(m.start(), m.end()) for rx in (_ISNAD_AN, _ISNAD_HADDATHANA) for m in rx.finditer(stripped)]
    prefix_rx = re.compile(
        r"(?:^|[\s،:؛.])(?:و?قال|وكذا قال|وهكذا قال|قاله|و?روي عن|"
        r"ونحوه عن|نحوه عن|ومثله عن|مثله عن|وهو قول|عن)\s*$"
    )
    suffix_rx = re.compile(r"^\s*[،:]?\s*(?:قال|في قوله|أنه قال|انه قال|أنه كان يقول|انه كان يقول|يقول)\b")
    for m in name_rx.finditer(stripped):
        name = m.group()
        before = stripped[max(0, m.start() - 90):m.start()]
        after = stripped[m.end():m.end() + 80]
        in_chain = any(a <= m.start() < b for a, b in chain_ranges)
        next_link = re.match(r"^\s*[،:]?\s*عن\b", after)
        # A later عن before the statement makes this name a transmitter, even
        # when it was introduced by قال (e.g. قال الضحاك: عن ابن عباس:).
        chain_tail = next((stripped[m.end():b] for a, b in chain_ranges if a <= m.start() < b), "")
        mid_chain = bool(next_link or re.search(r"\bعن\b", chain_tail))
        prefix = prefix_rx.search(before)
        suffix = suffix_rx.match(after)
        quoted = re.match(r"^\s*(?::\s*(?!عن\b)|[﴿{])", after)
        terminal_boundary = bool(re.match(r"^\s*[،:]?\s*$", after))
        route_source = bool(re.search(r"من طريق[^.؛:]{0,70}\bعن\s*$", before))
        if not (prefix or suffix or quoted or in_chain or route_source):
            continue
        if name in ("أبو سعيد", "ابو سعيد") and re.match(r"^\s+الأشج\b", after):
            continue
        role = "NARRATOR" if mid_chain or (in_chain and not (suffix or quoted or terminal_boundary)) else "SPEAKER"
        # Bare عن X needs a statement boundary, an explicit report formula,
        # or a terminal chain; otherwise X remains a transmitter.
        if prefix and prefix.group().strip() == "عن" and not (suffix or quoted or route_source or in_chain):
            role = "NARRATOR"
        if name in ("علي بن أبي طلحة", "علي بن ابي طلحة"):
            role = "NARRATOR"  # listed for transmission, not as an independent Tabi'i source
        oa, ob = _map_span(mapping, m.start(), m.end(), orig_len)
        hits.append({
            "family": families[name], "marker": name, "name": name,
            "role": role, "start": oa, "end": ob,
        })
    for m in re.finditer(r"(?<!\w)(?:النبي|رسول الله)(?!\w)", stripped):
        in_chain = any(a <= m.start() < b for a, b in chain_ranges)
        after = stripped[m.end():m.end() + 60]
        if in_chain and not re.match(r"^\s*[،:]?\s*عن\b", after):
            oa, ob = _map_span(mapping, m.start(), m.end(), orig_len)
            hits.append({"family": "HADITH", "marker": m.group(),
                         "role": "SPEAKER", "start": oa, "end": ob})
    return hits


def _isnad_hits(stripped: str, mapping: list[int], orig_len: int) -> list[dict]:
    hits: list[dict] = []
    for rx, label in ((_ISNAD_AN, "عن…عن"), (_ISNAD_HADDATHANA, "حدثنا…حدثنا")):
        for m in rx.finditer(stripped):
            oa, ob = _map_span(mapping, m.start(), m.end(), orig_len)
            hits.append(
                {
                    "family": "ISNAD",
                    "marker": label,
                    "start": oa,
                    "end": ob,
                    "stripped": m.group(),
                }
            )
    return hits


def _quran_quote_hits(text: str) -> list[dict]:
    hits: list[dict] = []
    for rx, label in ((_QURAN_CURLY, "{…}"), (_QURAN_ORNAMENT, "﴿…﴾")):
        for m in rx.finditer(text):
            hits.append(
                {
                    "family": "QURAN",
                    "marker": label,
                    "start": m.start(),
                    "end": m.end(),
                }
            )
    return hits


def _salawat_hits(text: str) -> list[dict]:
    hits: list[dict] = []
    start = 0
    while True:
        idx = text.find(_SALAWAT, start)
        if idx < 0:
            break
        hits.append(
            {"family": "HADITH", "marker": "ﷺ", "start": idx, "end": idx + 1}
        )
        start = idx + 1
    return hits


def _nearest_preceding_span(fn_start: int, spans: list[dict]) -> dict | None:
    best = None
    for s in spans:
        if s["end"] <= fn_start:
            if best is None or s["end"] > best["end"]:
                best = s
    return best


def _editor_footnote_evidence(
    apparatus: list[dict], spans: list[dict], tafsir_name: str = DEFAULT_TAFSIR_NAME
) -> list[dict]:
    """Attach footnotes to nearest preceding author span; detect grading words."""
    evidence: list[dict] = []
    for a in apparatus:
        if a["layer"] != "footnote":
            continue
        host = _nearest_preceding_span(a["start"], spans)
        stripped = remove_tashkeel(a["text"])
        grading: list[str] = []
        for g in GRADING_WORDS:
            if g in stripped:
                grading.append(g)
        evidence.append(
            {
                "family": "EDITOR",
                "marker": "editor_footnote",
                "start": a["start"],
                "end": a["end"],
                "text": a["text"],
                "attached_span_id": host["id"] if host else None,
                "grading": grading,
                "label_ar": f"حاشية المحقق — ليست من كلام {tafsir_name}",
            }
        )
    return evidence


def detect_span_markers(
    span: dict, apparatus: list[dict]
) -> list[dict]:
    text = span["text"]
    base = span["start"]
    stripped, mapping = _strip_map(text)
    hits: list[dict] = []

    # Absolute-offset helpers
    def abs_hits(raw_hits: list[dict]) -> list[dict]:
        out = []
        for h in raw_hits:
            hh = dict(h)
            hh["start"] = h["start"] + base
            hh["end"] = h["end"] + base
            hh["span_id"] = span["id"]
            out.append(hh)
        return out

    hits.extend(abs_hits(_quran_quote_hits(text)))
    hits.extend(
        abs_hits(_find_phrases(stripped, mapping, len(text), QURAN_PHRASES, "QURAN"))
    )
    for a in apparatus:
        if a["layer"] != "verse_ref":
            continue
        if span["end"] <= a["start"] <= span["end"] + 3:
            hits.append(
                {
                    "family": "QURAN",
                    "marker": "verse_ref",
                    "start": a["start"],
                    "end": a["end"],
                    "text": a["text"],
                    "via": "apparatus",
                    "span_id": span["id"],
                }
            )

    hits.extend(
        abs_hits(_find_phrases(stripped, mapping, len(text), HADITH_PHRASES, "HADITH"))
    )
    hits.extend(abs_hits(_salawat_hits(text)))

    hits.extend(abs_hits(_attribution_hits(stripped, mapping, len(text))))
    # Kaab also triggers ISRAILIYYAT when speech-proximity matched as TABIIN
    for h in list(hits):
        if h["family"] == "TABIIN" and h.get("role") == "SPEAKER" and "كعب" in h.get("name", h.get("marker", "")):
            hits.append({**h, "family": "ISRAILIYYAT", "marker": "كعب الأحبار (via TABIIN)"})

    hits.extend(abs_hits(_isnad_hits(stripped, mapping, len(text))))
    hits.extend(
        abs_hits(_find_phrases(stripped, mapping, len(text), LUGHA_PHRASES, "LUGHA"))
    )
    hits.extend(
        abs_hits(_find_phrases(stripped, mapping, len(text), QIRAAT_PHRASES, "QIRAAT"))
    )
    hits.extend(
        abs_hits(_find_phrases(stripped, mapping, len(text), NUZUL_PHRASES, "NUZUL"))
    )
    hits.extend(
        abs_hits(_find_phrases(stripped, mapping, len(text), SIRA_PHRASES, "SIRA"))
    )
    hits.extend(
        abs_hits(
            _find_phrases(stripped, mapping, len(text), ISRAILIYYAT_PHRASES, "ISRAILIYYAT")
        )
    )
    hits.extend(
        abs_hits(_find_phrases(stripped, mapping, len(text), RAY_PHRASES, "RAY"))
    )

    # Deduplicate identical (family, start, end, marker)
    seen: set[tuple] = set()
    uniq: list[dict] = []
    for h in hits:
        key = (h["family"], h["start"], h["end"], h["marker"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    uniq.sort(key=lambda h: (h["start"], h["end"], h["family"]))
    return uniq


def build_markers_for_window(
    window: dict, tafsir_name: str = DEFAULT_TAFSIR_NAME
) -> dict:
    spans = window["spans"]
    apparatus = _normalize_apparatus(window.get("apparatus") or [])
    per_span: list[dict] = []
    all_hits: list[dict] = []
    counts: dict[str, int] = {}

    for s in spans:
        hits = detect_span_markers(s, apparatus)
        per_span.append({"span_id": s["id"], "markers": hits})
        all_hits.extend(hits)
        for h in hits:
            counts[h["family"]] = counts.get(h["family"], 0) + 1

    editor_ev = _editor_footnote_evidence(apparatus, spans, tafsir_name=tafsir_name)
    for e in editor_ev:
        counts["EDITOR"] = counts.get("EDITOR", 0) + 1

    payload = {
        "window_id": window["window_id"],
        "ayah": window["ayah"],
        "span_count": len(spans),
        "family_counts": counts,
        "spans": per_span,
        "editor_footnote_evidence": editor_ev,
        "isnad_ranges": [
            {"start": h["start"], "end": h["end"], "span_id": h["span_id"], "marker": h["marker"]}
            for h in all_hits
            if h["family"] == "ISNAD"
        ],
    }
    return payload


def build_markers(tafsir_name: str = DEFAULT_TAFSIR_NAME) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for path in sorted(WINDOWS_DIR.glob("*.json")):
        window = _read_json(path)
        payload = build_markers_for_window(window, tafsir_name=tafsir_name)
        out = OUT_DIR / path.name
        out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        counts = payload["family_counts"]
        summary[window["window_id"]] = counts
        parts = " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"{window['window_id']}: {parts or '(no markers)'}")
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect methodology markers per window.")
    p.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help="Base dir with windows/ (default: data/v2)",
    )
    p.add_argument(
        "--tafsir-name",
        default=DEFAULT_TAFSIR_NAME,
        help="Arabic author name used in editor labels (default: ابن كثير)",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    configure(args.base)
    build_markers(tafsir_name=args.tafsir_name)
