"""Build self-contained classifier input packets (one per window) + prompt doc."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from textcore import read_json as _read_json, resolve_base as _resolve_base

DEFAULT_BASE = "data/v2"
DEFAULT_TAFSIR_NAME = "ابن كثير"

WINDOWS_DIR = ROOT / "data" / "v2" / "windows"
MARKERS_DIR = ROOT / "data" / "v2" / "markers"
OUT_DIR = ROOT / "data" / "v2" / "packets"
PROMPT_PATH = ROOT / "method" / "classifier_prompt_v2.md"
DEFAULT_V2_BASE = (ROOT / "data" / "v2").resolve()

# Apparatus subtypes that are editor material (not layout, not verse_ref→QURAN).
_EDITOR_APPARATUS = frozenset({"footnote", "editor_bracket", "unknown_marker"})
_LAYOUT_SKIP = frozenset({"layout", "<br>", "<br/>", "<br />"})


def _definitions_ar(tafsir_name: str) -> list[dict]:
    return [
        {
            "id": "M_QURAN",
            "name_ar": "القرآن بالقرآن",
            "when": "آية أخرى تبيّن معنى الآية المفسَّرة.",
            "exclude": "اقتباس آية داخل حديث أو مجرد نظير موضوعي.",
            "markers": "كما قال تعالى، وقال تعالى، قوله تعالى، {…}، [سورة: ن]",
        },
        {
            "id": "M_SUNNAH",
            "name_ar": "السنة",
            "when": "قول أو فعل أو تقرير نبوي يبيّن معنى الآية أو فضلها المتصل بها.",
            "exclude": "ذكر النبي في إسناد أو سياق عابر فقط.",
            "markers": "قال رسول الله، أن النبي، رواه، أخرجه، حدثنا، ﷺ",
        },
        {
            "id": "M_SAHABA",
            "name_ar": "الصحابة",
            "when": "قول الصحابي نفسه مادة تفسيرية.",
            "exclude": "اسم الصحابي راوياً فقط داخل إسناد.",
            "markers": "قال ابن عباس، قال علي، عن أبيّ بن كعب + قرب فعل القول",
        },
        {
            "id": "M_TABIIN",
            "name_ar": "التابعون",
            "when": "قول التابعي نفسه يشرح الآية.",
            "exclude": "وروده راوياً في السند.",
            "markers": "قال مجاهد، قال قتادة، قال الحسن، عن سعيد بن جبير",
        },
        {
            "id": "M_LUGHA",
            "name_ar": "اللغة والغريب والشعر شاهداً",
            "when": "شرح لفظ أو استعمال عربي أو بيت يُحتج به للمعنى.",
            "exclude": "شرح المحقق في الحاشية، أو بيت للزينة.",
            "markers": "أي، معناه، والعرب تقول، قال الشاعر، وأنشد",
        },
        {
            "id": "M_QIRAAT",
            "name_ar": "القراءات",
            "when": "اختلاف قراءة يُستخدم لبيان اللفظ أو المعنى.",
            "exclude": "اختلاف النسخ أو الضبط الطباعي.",
            "markers": "قرأ، قراءة، وفي قراءة، قرأه",
        },
        {
            "id": "M_NUZUL",
            "name_ar": "سبب النزول",
            "when": "خبر يربط حدثاً أو سؤالاً بنزول الآية.",
            "exclude": "حدث تاريخي يشرح الخلفية دون دعوى النزول.",
            "markers": "نزلت في، سبب نزول، فأنزل الله، فنزلت",
        },
        {
            "id": "M_SIRA",
            "name_ar": "المغازي والسيرة",
            "when": "واقعة من السيرة تُستخدم لشرح خطاب الآية أو تطبيقه.",
            "exclude": "ورود اسم غزوة عرضاً.",
            "markers": "يوم بدر، غزوة، يوم أحد، خرج رسول الله",
        },
        {
            "id": "M_ISRAILIYYAT",
            "name_ar": "الإسرائيليات",
            "when": f"مادة يعزوها النص لأهل الكتاب أو بني إسرائيل، أو يصنّفها {tafsir_name} كذلك.",
            "exclude": "غرابة القصة وحدها.",
            "markers": "كعب الأحبار، وهب بن منبه، أهل الكتاب، بني إسرائيل، الإسرائيليات",
        },
        {
            "id": "M_RAY",
            "name_ar": "الرأي والاجتهاد",
            "when": f"استنتاج {tafsir_name} أو ترجيحه التفسيري.",
            "exclude": "مجرد نقل حكم غيره، أو عزو حديث وتسميته رأياً.",
            "markers": "والظاهر، والصحيح، والأقرب، قلت، والله أعلم",
        },
    ]


def _certainty_rules_ar(tafsir_name: str) -> dict:
    return {
        "explicit": f"علامة نصية + spans لدليل الوظيفة + نسبة واضحة للقائل؛ لا يناقضها حكم {tafsir_name}.",
        "strong": "القرينة قد تمتد عبر spans متجاورة، لكن شاهد الوظيفة ونسبة القائل بلا بديل معقول. الحاشية قد تؤكد تخريجاً أو درجة، ولا تنشئ منهجاً من تلقائها.",
        "weak": "علامة بلا وظيفة واضحة، أو وظيفة مرجحة مع التباس القائل/الحدود/موقف المؤلف.",
        "insufficient": "لا شاهد مُحال إليه، أو تعارض غير محلول، أو نص مقطوع قبل موضع الدلالة — امتنع عن التصنيف.",
    }


# Back-compat aliases for importers / tests that expect module-level constants.
DEFINITIONS_AR = _definitions_ar(DEFAULT_TAFSIR_NAME)
CERTAINTY_RULES_AR = _certainty_rules_ar(DEFAULT_TAFSIR_NAME)

OUTPUT_SCHEMA = {
    "window": "<window_id>",
    "moves": [
        {
            "move_id": "m01",
            "span_ids": ["s002", "s003"],
            "primary": "M_QURAN|M_SUNNAH|M_SAHABA|M_TABIIN|M_LUGHA|M_QIRAAT|M_NUZUL|M_SIRA|M_ISRAILIYYAT|M_RAY|null",
            "secondary": [],
            "content_tags": [],
            "certainty": "explicit|strong|weak|insufficient",
            "evidence_span_ids": ["s002"],
            "author_verdict_span_ids": [],
            "references": {"verses": [], "hadith": [], "persons": []},
            "alternatives": [],
            "rationale_ar": "≤25 words, no quotes >4 words",
        }
    ],
}






def configure(base: str | Path = DEFAULT_BASE) -> Path:
    """Point windows/markers/packets dirs at <base>. Returns resolved base path."""
    global WINDOWS_DIR, MARKERS_DIR, OUT_DIR
    base_path = _resolve_base(base)
    WINDOWS_DIR = base_path / "windows"
    MARKERS_DIR = base_path / "markers"
    OUT_DIR = base_path / "packets"
    return base_path


def _apparatus_layer(a: dict) -> str | None:
    if a.get("kind") == "layout":
        return None
    layer = a.get("layer") or a.get("subtype")
    text = (a.get("text") or "").strip()
    if not layer or layer in _LAYOUT_SKIP or text in _LAYOUT_SKIP:
        return None
    return layer


def _prompt_markdown(tafsir_name: str = DEFAULT_TAFSIR_NAME) -> str:
    definitions = _definitions_ar(tafsir_name)
    certainty = _certainty_rules_ar(tafsir_name)
    lines = [
        f"# موجه المصنّف — فهرسة مناهج {tafsir_name} (v2)",
        "",
        "## المهمة",
        f"أنت مصنّف واحد لحركات تفسيرية داخل نوافذ من تفسير {tafsir_name}.",
        "لكل حزمة إدخال (packet) أعِد JSON فقط وفق المخطط أدناه.",
        "",
        "## قواعد صارمة",
        "1. أعد **معرّفات spans فقط** (`s001`…) — **لا تعِد كتابة النص** ولا تقتبس أكثر من 4 كلمات في `rationale_ar`.",
        "2. وسم **وظيفة النص في تفسير الآية**، لا الألفاظ الظاهرة وحدها.",
        "3. منهج رئيسي واحد لكل حركة (`primary`)، أو `null` للتخريج المحض / الامتناع. مناهج ثانوية اختيارية عند مساهمة مستقلة مثبتة.",
        "4. إذا نقص الدليل: `certainty: \"insufficient\"` و`primary: null` — **الامتناع إجابة صحيحة**.",
        f"5. حاشية المحقق دليل مساعد لنسبة الخبر أو درجته فقط؛ **ليست من كلام {tafsir_name}** ولا تنشئ منهجاً وحدها.",
        "6. آية داخل حديث ≠ قرآن بالقرآن. اسم صحابي/تابعي داخل إسناد ≠ قولهما. غرابة القصة ≠ إسرائيليات.",
        "7. `rationale_ar` ≤ 25 كلمة.",
        "",
        "## التعريفات التشغيلية",
        "",
    ]
    for d in definitions:
        lines.append(f"### {d['id']} — {d['name_ar']}")
        lines.append(f"- يُدرج متى: {d['when']}")
        lines.append(f"- يُستبعد: {d['exclude']}")
        lines.append(f"- علامات مرشّحة: {d['markers']}")
        lines.append("")
    lines.append("## مستويات اليقين")
    lines.append("")
    for k, v in certainty.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## مخطط الإخراج (JSON)")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("الحقل `window` يجب أن يطابق `window_id` في الحزمة. لا تضف حقولاً أخرى.")
    lines.append("")
    return "\n".join(lines)


def _editor_label(tafsir_name: str, layer: str) -> str:
    if layer == "footnote":
        return f"حاشية المحقق — ليست من كلام {tafsir_name}"
    return f"إضافة المحقق — ليست من كلام {tafsir_name}"


def build_packet(
    window: dict, markers: dict, tafsir_name: str = DEFAULT_TAFSIR_NAME
) -> dict:
    marker_by_span = {s["span_id"]: s["markers"] for s in markers["spans"]}
    span_payload = []
    for s in window["spans"]:
        span_payload.append(
            {
                "id": s["id"],
                "start": s["start"],
                "end": s["end"],
                "text": s["text"],
                "markers": marker_by_span.get(s["id"], []),
            }
        )

    # Footnotes from markers (identical path for Ibn Kathir).
    editor = []
    seen_ranges: set[tuple[int, int]] = set()
    for e in markers.get("editor_footnote_evidence") or []:
        key = (e["start"], e["end"])
        seen_ranges.add(key)
        editor.append(
            {
                "label_ar": _editor_label(tafsir_name, "footnote"),
                "attached_span_id": e.get("attached_span_id"),
                "start": e["start"],
                "end": e["end"],
                "text": e["text"],
                "grading": e.get("grading") or [],
            }
        )

    # Extra apparatus (editor_bracket / unknown_marker) — never layout <br>.
    # For default Ibn Kathir this adds nothing new beyond footnotes already present,
    # because v2 markers only emit footnotes and Ibn Kathir packets historically
    # listed only those; editor_bracket stays out of editor_footnote_evidence.
    # Multi windows may carry unknown_marker / editor_bracket that should be labeled
    # إضافة المحقق without marking any author span "editor-only".
    if tafsir_name != DEFAULT_TAFSIR_NAME:
        spans = window.get("spans") or []

        def _nearest(fn_start: int) -> str | None:
            best = None
            for s in spans:
                if s["end"] <= fn_start:
                    if best is None or s["end"] > best["end"]:
                        best = s
            return best["id"] if best else None

        for a in window.get("apparatus") or []:
            layer = _apparatus_layer(a)
            if layer is None or layer == "verse_ref":
                continue
            if layer not in _EDITOR_APPARATUS:
                continue
            if layer == "footnote":
                continue  # already from markers
            key = (a["start"], a["end"])
            if key in seen_ranges:
                continue
            seen_ranges.add(key)
            editor.append(
                {
                    "label_ar": _editor_label(tafsir_name, layer),
                    "attached_span_id": _nearest(a["start"]),
                    "start": a["start"],
                    "end": a["end"],
                    "text": a["text"],
                    "grading": [],
                }
            )

    return {
        "window_id": window["window_id"],
        "ayah": window["ayah"],
        "source_file": window["source_file"],
        "source_sha256": window.get("source_sha256"),
        "instructions_ar": (
            "أعد JSON فقط. معرّفات spans دون نص. "
            "منهج رئيسي واحد أو null. امتنع (insufficient) عند غياب الدليل. "
            f"الحاشية ليست كلام {tafsir_name}."
        ),
        "definitions": _definitions_ar(tafsir_name),
        "certainty_rules": _certainty_rules_ar(tafsir_name),
        "output_schema": OUTPUT_SCHEMA,
        "isnad_ranges": markers.get("isnad_ranges") or [],
        "spans": span_payload,
        "editor_footnote_evidence": editor,
    }


def build_packets(tafsir_name: str = DEFAULT_TAFSIR_NAME, write_prompt: bool = True) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if write_prompt:
        PROMPT_PATH.write_bytes(_prompt_markdown(tafsir_name).encode("utf-8"))
        print(f"wrote {PROMPT_PATH.relative_to(ROOT).as_posix()}")

    summary = {}
    for path in sorted(WINDOWS_DIR.glob("*.json")):
        window = _read_json(path)
        markers = _read_json(MARKERS_DIR / path.name)
        packet = build_packet(window, markers, tafsir_name=tafsir_name)
        out = OUT_DIR / path.name
        out.write_bytes(json.dumps(packet, ensure_ascii=False, indent=2).encode("utf-8"))
        summary[window["window_id"]] = {
            "spans": len(packet["spans"]),
            "editor_notes": len(packet["editor_footnote_evidence"]),
        }
        print(
            f"{window['window_id']}: spans={len(packet['spans'])} "
            f"editor_notes={len(packet['editor_footnote_evidence'])}"
        )
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build classifier input packets per window.")
    p.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help="Base dir with windows/ and markers/ (default: data/v2)",
    )
    p.add_argument(
        "--tafsir-name",
        default=DEFAULT_TAFSIR_NAME,
        help="Arabic author name in packet labels (default: ابن كثير)",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    base_path = configure(args.base)
    write_prompt = base_path == DEFAULT_V2_BASE
    build_packets(tafsir_name=args.tafsir_name, write_prompt=write_prompt)
