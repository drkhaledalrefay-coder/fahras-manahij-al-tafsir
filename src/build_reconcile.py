"""Build the human reconciliation screen for Ayat al-Kursi (checkpoint B).

No model runs. The script only reads pinned inputs and writes:
  web/reconcile_data.json
  web/reconcile.html

Comparison colors are a visual aid for the reviewer. They are not a
decision that the passage is reconciled.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from normalize import l1_normalize  # noqa: E402

SOURCE_REL = "data/raw/tafsircenter/2_255.txt"
WINDOW_KEY = "2_255"
SLACK = 6
ELLIPSIS_RE = re.compile(r"\.\.\.|…")
SENTENCE_BOUND = set(".!?\u061f\u061b\u2026\n\r\u06d4")
EDGE_PUNCT = "\"'«»“”‘’()[]{}:،,.؛؟!?…\\-–—"

LAYER_AR = {
    "footnote": "حاشية المحقق",
    "editor_bracket": "قوس المحقق",
    "verse_ref": "إحالة آية",
}

TAG_AR = {
    "S_QURAN": "تفسير القرآن بالقرآن",
    "S_SUNNAH": "تفسير القرآن بالسنة",
    "S_SAHABA": "أقوال الصحابة",
    "S_TABIIN": "أقوال التابعين",
    "S_LUGHA": "اللغة",
    "S_RAY": "الاجتهاد والرأي",
    "S_IRAB": "الإعراب",
    "C_NUZUL": "أسباب النزول",
    "C_FIQH": "فقه وأحكام",
    "C_BALAGHA": "بلاغة",
    "C_SHIR": "شعر",
    "C_ISRAILIYYAT": "إسرائيليات",
    "C_FADAIL": "فضائل القرآن/الآية",
    "C_TAKHRIJ": "تخريج/حكم حديثي",
    "C_TAFSIR": "بيان معنى",
}

SET_SYSTEM = "مخرجات النظام"
SET_EXCEL = "جدول الفريق (Excel)"


def read_exact(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_source() -> tuple[str, str]:
    path = ROOT / SOURCE_REL
    blob = path.read_bytes()
    text = read_exact(path)
    if text.encode("utf-8") != blob:
        raise SystemExit(
            f"{SOURCE_REL}: reading with utf-8 and newline='' does not round-trip to the file bytes"
        )
    digest = hashlib.sha256(blob).hexdigest()
    manifest = load_json(ROOT / "data" / "raw" / "manifest.json")
    pinned = None
    for entry in manifest["entries"]:
        if entry.get("path") == SOURCE_REL:
            pinned = entry.get("sha256")
            break
    if not pinned:
        raise SystemExit(f"manifest has no sha256 for {SOURCE_REL}")
    if digest != pinned:
        raise SystemExit(
            f"sha256 mismatch for {SOURCE_REL}: file {digest} != manifest {pinned}"
        )
    return text, digest


def layer_index(ranges: list[dict]):
    ranges = sorted(ranges, key=lambda item: (item["start"], item["end"]))

    def at(pos: int) -> str:
        lo, hi = 0, len(ranges) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            row = ranges[mid]
            if pos < row["start"]:
                hi = mid - 1
            elif pos >= row["end"]:
                lo = mid + 1
            else:
                return row["layer"]
        raise SystemExit(f"no layer covers source offset {pos}")

    return ranges, at


def tokenize(src: str, base: int, layer_at=None) -> list[dict]:
    words: list[dict] = []
    index = 0
    length = len(src)
    while index < length:
        while index < length and src[index].isspace():
            index += 1
        if index >= length:
            break
        end = index
        while end < length and not src[end].isspace():
            end += 1
        raw = src[index:end]
        parts = [part for part in l1_normalize(raw).split(" ") if part]
        layer = layer_at(base + index) if layer_at else None
        expanded = len(parts) > 1
        for part in parts:
            words.append(
                {
                    "raw": raw,
                    "norm": part,
                    "start": base + index,
                    "end": base + end,
                    "layer": layer,
                    "expanded": expanded,
                }
            )
        index = end
    return words


def surface(words: list[dict]) -> list[str]:
    seen: set[tuple[int, int]] = set()
    out: list[str] = []
    for word in words:
        key = (word["start"], word["end"])
        if key in seen:
            continue
        seen.add(key)
        out.append(word["raw"])
    return out


def norms_of(words: list[dict]) -> list[str]:
    if not words:
        return []
    # Expanded tokens share one surface form; keep one norm sequence for alignment
    # but collapse only the displayed surface, not the norm list.
    return [word["norm"] for word in words]


def pretty(raw: str) -> str:
    text = raw.strip()
    while text and text[0] in EDGE_PUNCT:
        text = text[1:]
    while text and text[-1] in EDGE_PUNCT:
        text = text[:-1]
    return text or raw.strip() or raw


def describe_char(char: str) -> str:
    if char == " ":
        return "مسافة"
    if char in "\r\n":
        return "سطر جديد"
    if char == "\t":
        return "مسافة جدول"
    if char == "\u00ac":
        return "علامة بداية الحاشية (¬)"
    if char == "\u00a5":
        return "علامة نهاية الحاشية (¥)"
    return f"«{char}»"


def sentence_issues(text: str, start: int, end: int) -> list[str]:
    issues: list[str] = []
    if start > 0 and text[start - 1] not in SENTENCE_BOUND:
        issues.append(
            "بداية الوحدة ليست على حد جملة: الحرف السابق "
            f"{describe_char(text[start - 1])} وليس علامة جملة أو سطرًا جديدًا."
        )
    if end < len(text) and text[end] not in SENTENCE_BOUND:
        issues.append(
            "نهاية الوحدة ليست على حد جملة: الحرف التالي "
            f"{describe_char(text[end])} وليس علامة جملة أو سطرًا جديدًا."
        )
    return issues


def join_ar(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]}، و{parts[1]}"
    return "، ".join(parts[:-1]) + "، و" + parts[-1]


def quoted_words(words: list[str]) -> str:
    cleaned = [pretty(word) for word in words if pretty(word)]
    if not cleaned:
        return "—"
    return " ".join(cleaned)


def summary_from_diffs(diffs: list[dict]) -> str:
    variants = [item for item in diffs if item["kind"] == "variant"]
    missing = [item for item in diffs if item["kind"] == "missing_in_annotation"]
    extra = [item for item in diffs if item["kind"] == "extra_in_annotation"]
    bits: list[str] = []
    if variants:
        word_n = sum(
            max(len(item["annotation_words"]), len(item["source_words"]), 1)
            for item in variants
        )
        if len(variants) == 1 and word_n == 1:
            head = "كلمة واحدة مختلفة"
        elif word_n == 2:
            head = "كلمتان مختلفتان"
        else:
            head = f"{word_n} كلمات مختلفة"
        parts = []
        for item in variants:
            parts.append(
                f"«{quoted_words(item['annotation_words'])}» في النص الموسوم مقابل "
                f"«{quoted_words(item['source_words'])}» في المصدر"
            )
        bits.append(head + ": " + join_ar(parts))
    if missing:
        words = [pretty(word) for item in missing for word in item["source_words"]]
        bits.append("في المصدر وليس في النص الموسوم: " + " ".join(f"«{word}»" for word in words))
    if extra:
        words = [pretty(word) for item in extra for word in item["annotation_words"]]
        bits.append("في النص الموسوم وليس في المصدر: " + " ".join(f"«{word}»" for word in words))
    if not bits:
        return ""
    return ". ".join(bits) + "."


def tag_objects(codes: list[str]) -> list[dict]:
    return [{"code": code, "label_ar": TAG_AR.get(code, code)} for code in codes]


def plain_tags(labels: list[str]) -> list[dict]:
    return [{"code": None, "label_ar": label} for label in labels]


def word_public(word: dict, index: int) -> dict:
    item = {
        "i": index,
        "start": word["start"],
        "end": word["end"],
        "norm": word["norm"],
        "layer": word["layer"],
    }
    if word["expanded"]:
        item["expanded"] = True
    return item


def fragment_public(words: list[dict]) -> dict:
    public = []
    for word in words:
        item = {"start": word["start"], "end": word["end"], "norm": word["norm"]}
        if word["expanded"]:
            item["expanded"] = True
        public.append(item)
    return {"words": public}


def coalesce(runs: list[dict], text: str) -> list[dict]:
    merged: list[dict] = []
    for run in runs:
        if run["start"] == run["end"] or run.get("kind") == "chip":
            merged.append(run)
            continue
        if (
            merged
            and merged[-1].get("kind") == run["kind"]
            and merged[-1].get("pair") == run.get("pair")
            and merged[-1]["start"] != merged[-1]["end"]
            and run["start"] >= merged[-1]["end"]
            and text[merged[-1]["end"] : run["start"]].strip() == ""
        ):
            merged[-1]["end"] = run["end"]
            if run.get("title") and not merged[-1].get("title"):
                merged[-1]["title"] = run["title"]
            continue
        merged.append(dict(run))
    return merged


def first_label(runs: list[dict], kind: str) -> None:
    seen = False
    for run in runs:
        if run.get("kind") != kind:
            continue
        if seen:
            run.pop("label", None)
        else:
            seen = True


class Aligner:
    def __init__(self, source: str, author: list[dict], layers: list[dict]):
        self.source = source
        self.author = author
        self.author_norms = [word["norm"] for word in author]
        self.layers = layers

    def candidates(self, norms: list[str], start_from: int) -> list[tuple[int, int]]:
        count = len(norms)
        found: set[tuple[int, int]] = set()

        def add(start: int, end: int) -> None:
            if start_from <= start < end <= len(self.author):
                length = end - start
                if max(1, count - SLACK) <= length <= count + SLACK:
                    found.add((start, end))

        hits = 0
        if count >= 2:
            for index in range(count - 1):
                left, right = norms[index], norms[index + 1]
                for pos in range(start_from, len(self.author) - 1):
                    if self.author_norms[pos] != left or self.author_norms[pos + 1] != right:
                        continue
                    hits += 1
                    for pre_delta in range(-SLACK, SLACK + 1):
                        for post_delta in range(-SLACK, SLACK + 1):
                            pre = index + pre_delta
                            post = count - index - 2 + post_delta
                            if pre < 0 or post < 0:
                                continue
                            add(pos - pre, pos + 2 + post)
        if hits == 0:
            for index, word in enumerate(norms):
                for pos in range(start_from, len(self.author)):
                    if self.author_norms[pos] != word:
                        continue
                    for pre_delta in range(-SLACK, SLACK + 1):
                        for post_delta in range(-SLACK, SLACK + 1):
                            pre = index + pre_delta
                            post = count - index - 1 + post_delta
                            if pre < 0 or post < 0:
                                continue
                            add(pos - pre, pos + 1 + post)
        return list(found)

    def score(self, norms: list[str], start: int, end: int):
        window = self.author_norms[start:end]
        matcher = SequenceMatcher(None, norms, window, autojunk=False)
        ops = list(matcher.get_opcodes())
        equal = deleted = inserted = replaced = 0
        for tag, a1, a2, b1, b2 in ops:
            if tag == "equal":
                equal += a2 - a1
            elif tag == "delete":
                deleted += a2 - a1
            elif tag == "insert":
                inserted += b2 - b1
            else:
                replaced += a2 - a1
        key = (equal, -deleted, -inserted, -replaced, matcher.ratio(), -start, -(end - start))
        return key, ops

    def place(self, fragment: list[dict], start_from: int):
        norms = [word["norm"] for word in fragment]
        best = None
        best_ops = None
        for start, end in self.candidates(norms, start_from):
            key, ops = self.score(norms, start, end)
            if best is None or key > best[0]:
                best = (key, start, end)
                best_ops = ops
        if best is None:
            return None
        return {"start": best[1], "end": best[2], "ops": best_ops, "key": best[0]}

    def apparatus_inside(self, start_char: int, end_char: int) -> list[dict]:
        found = []
        for row in self.layers:
            if row["layer"] == "author":
                continue
            if row["start"] >= start_char and row["end"] <= end_char and row["start"] < row["end"]:
                found.append(row)
        return found


def make_diff(kind: str, ann_words: list[dict], src_words: list[dict], source_at: tuple[int, int], ann_at: tuple[int, int], pair: int) -> dict:
    return {
        "kind": kind,
        "annotation_words": surface(ann_words),
        "source_words": surface(src_words),
        "annotation_norms": [word["norm"] for word in ann_words],
        "source_norms": [word["norm"] for word in src_words],
        "source_start": source_at[0],
        "source_end": source_at[1],
        "annotation_start": ann_at[0],
        "annotation_end": ann_at[1],
        "pair": pair,
    }


def pair_title(diff: dict) -> str:
    ann = quoted_words(diff["annotation_words"])
    src = quoted_words(diff["source_words"])
    if diff["kind"] == "variant":
        return f"في النص الموسوم: «{ann}» — في المصدر: «{src}»"
    if diff["kind"] == "missing_in_annotation":
        return f"في المصدر وليس في النص الموسوم: «{src}»"
    return f"في النص الموسوم وليس في المصدر: «{ann}»"


def align_excel_unit(unit_text: str, aligner: Aligner) -> dict:
    pieces: list[tuple[int, int]] = []
    cursor = 0
    for match in ELLIPSIS_RE.finditer(unit_text):
        pieces.append((cursor, match.start()))
        cursor = match.end()
    pieces.append((cursor, len(unit_text)))
    fragments: list[list[dict]] = []
    for start, end in pieces:
        words = [word for word in tokenize(unit_text[start:end], start) if word["norm"]]
        if words:
            fragments.append(words)
    leading = bool(re.match(r"^\s*(\.\.\.|…)", unit_text))
    trailing = bool(re.search(r"(\.\.\.|…)\s*$", unit_text))

    placed = []
    search_from = 0
    diffs: list[dict] = []
    pair = 1
    diacritics = False
    source_runs: list[dict] = []
    ann_runs: list[dict] = []

    for fragment in fragments:
        placement = aligner.place(fragment, search_from)
        if placement is None:
            diffs.append(
                make_diff(
                    "extra_in_annotation",
                    fragment,
                    [],
                    (0, 0),
                    (fragment[0]["start"], fragment[-1]["end"]),
                    pair,
                )
            )
            pair += 1
            continue
        start, end = placement["start"], placement["end"]
        for tag, a1, a2, b1, b2 in placement["ops"]:
            ann_slice = fragment[a1:a2]
            src_slice = aligner.author[start + b1 : start + b2]
            if tag == "equal":
                for offset in range(a2 - a1):
                    ann_word = fragment[a1 + offset]
                    src_word = aligner.author[start + b1 + offset]
                    if ann_word["raw"] != src_word["raw"]:
                        diacritics = True
                    source_runs.append(
                        {"start": src_word["start"], "end": src_word["end"], "kind": "equal", "pair": None}
                    )
                    ann_runs.append(
                        {"start": ann_word["start"], "end": ann_word["end"], "kind": "equal", "pair": None}
                    )
                continue
            kind = {
                "replace": "variant",
                "insert": "missing_in_annotation",
                "delete": "extra_in_annotation",
            }[tag]
            if src_slice:
                src_at = (src_slice[0]["start"], src_slice[-1]["end"])
            elif start + b1 < len(aligner.author):
                point = aligner.author[start + b1]["start"]
                src_at = (point, point)
            elif start + b1 > 0:
                point = aligner.author[min(start + b1, len(aligner.author)) - 1]["end"]
                src_at = (point, point)
            else:
                src_at = (0, 0)
            if ann_slice:
                ann_at = (ann_slice[0]["start"], ann_slice[-1]["end"])
            elif a1 < len(fragment):
                point = fragment[a1]["start"]
                ann_at = (point, point)
            elif fragment:
                point = fragment[-1]["end"]
                ann_at = (point, point)
            else:
                ann_at = (0, 0)
            diff = make_diff(kind, ann_slice, src_slice, src_at, ann_at, pair)
            diffs.append(diff)
            title = pair_title(diff)
            label = f"discrepancy {pair}"
            if kind == "extra_in_annotation":
                ann_runs.append(
                    {
                        "start": ann_at[0],
                        "end": ann_at[1],
                        "kind": "discrepancy",
                        "label": label,
                        "title": title,
                        "pair": pair,
                    }
                )
                source_runs.append(
                    {
                        "start": src_at[0],
                        "end": src_at[1],
                        "kind": "chip",
                        "label": label,
                        "title": title,
                        "pair": pair,
                        "chip_text": "زائد في الموسوم: " + " ".join(f"«{pretty(word)}»" for word in diff["annotation_words"]),
                    }
                )
            elif kind == "missing_in_annotation":
                source_runs.append(
                    {
                        "start": src_at[0],
                        "end": src_at[1],
                        "kind": "discrepancy",
                        "label": label,
                        "title": title,
                        "pair": pair,
                    }
                )
                ann_runs.append(
                    {
                        "start": ann_at[0],
                        "end": ann_at[1],
                        "kind": "chip",
                        "label": label,
                        "title": title,
                        "pair": pair,
                        "chip_text": "ناقص من الموسوم: " + " ".join(f"«{pretty(word)}»" for word in diff["source_words"]),
                    }
                )
            else:
                source_runs.append(
                    {
                        "start": src_at[0],
                        "end": src_at[1],
                        "kind": "discrepancy",
                        "label": label,
                        "title": title,
                        "pair": pair,
                    }
                )
                ann_runs.append(
                    {
                        "start": ann_at[0],
                        "end": ann_at[1],
                        "kind": "discrepancy",
                        "label": label,
                        "title": title,
                        "pair": pair,
                    }
                )
            pair += 1
        placed.append({"start": start, "end": end, "words": fragment})
        search_from = end

    gaps = []
    for left, right in zip(placed, placed[1:]):
        if right["start"] <= left["end"]:
            continue
        gap_start = aligner.author[left["end"] - 1]["end"]
        gap_end = aligner.author[right["start"]]["start"]
        if gap_end <= gap_start:
            continue
        gap_text = aligner.source[gap_start:gap_end]
        has_letter = any(("\u0600" <= char <= "\u06ff") or char.isalnum() for char in gap_text)
        if not has_letter:
            continue
        gaps.append({"start": gap_start, "end": gap_end, "role": "elision"})
        source_runs.append(
            {
                "start": gap_start,
                "end": gap_end,
                "kind": "elision",
                "label": "محذوف من النص الموسوم",
                "title": "محذوف من النص الموسوم",
                "pair": None,
            }
        )

    apparatus = []
    for place in placed:
        if place["end"] <= place["start"]:
            continue
        char_start = aligner.author[place["start"]]["start"]
        char_end = aligner.author[place["end"] - 1]["end"]
        for row in aligner.apparatus_inside(char_start, char_end):
            apparatus.append({"start": row["start"], "end": row["end"], "layer": row["layer"], "role": "apparatus"})
            source_runs.append(
                {
                    "start": row["start"],
                    "end": row["end"],
                    "kind": "apparatus",
                    "label": LAYER_AR.get(row["layer"], row["layer"]),
                    "title": LAYER_AR.get(row["layer"], row["layer"]),
                    "pair": None,
                }
            )

    for match in ELLIPSIS_RE.finditer(unit_text):
        ann_runs.append(
            {
                "start": match.start(),
                "end": match.end(),
                "kind": "elision_marker",
                "label": "حذف",
                "title": "علامة حذف في النص الموسوم",
                "pair": None,
            }
        )

    if placed:
        outer_start = aligner.author[placed[0]["start"]]["start"]
        outer_end = aligner.author[placed[-1]["end"] - 1]["end"]
    else:
        outer_start = outer_end = 0

    reasons: list[str] = []
    elided = len(fragments) > 1 or leading or trailing or bool(gaps)
    if len(fragments) > 1 or leading or trailing:
        reasons.append("النص الموسوم فيه حذف مشار إليه بـ «...».")
    if gaps:
        reasons.append("مواضع الحذف من كلام المصدر معلّمة في النص الأصلي.")
    if trailing:
        reasons.append("النص الموسوم ينتهي بعلامة حذف، ولم يُفرض مدى بعد آخر كلمة ظاهرة.")
    if leading:
        reasons.append("النص الموسوم يبدأ بعلامة حذف، ولم يُفرض مدى قبل أول كلمة ظاهرة.")
    if apparatus:
        names = join_ar(sorted({LAYER_AR.get(item["layer"], item["layer"]) for item in apparatus}))
        reasons.append(f"داخل المدى {names}، وهي ليست جزءًا من النص الموسوم.")
    reasons.extend(sentence_issues(aligner.source, outer_start, outer_end))

    diff_sentence = summary_from_diffs(diffs)
    if diff_sentence:
        reasons.insert(0, diff_sentence.rstrip("."))
    if diffs:
        color = "discrepancy"
    elif elided or apparatus or any(reason.startswith("بداية") or reason.startswith("نهاية") for reason in reasons):
        color = "highlighted"
    else:
        color = "matched"

    paint_kind = {"matched": "matched", "highlighted": "highlighted"}.get(color)
    if paint_kind:
        for run in source_runs:
            if run["kind"] == "equal":
                run["kind"] = paint_kind
                run["label"] = paint_kind
        for run in ann_runs:
            if run["kind"] == "equal":
                run["kind"] = paint_kind
                run["label"] = paint_kind
    else:
        source_runs = [run for run in source_runs if run["kind"] != "equal"]
        ann_runs = [run for run in ann_runs if run["kind"] != "equal"]

    source_runs = coalesce(source_runs, aligner.source)
    ann_runs = coalesce(ann_runs, unit_text)
    if paint_kind:
        first_label(source_runs, paint_kind)
        first_label(ann_runs, paint_kind)

    if color == "matched":
        if diacritics:
            summary = (
                "الكلمات تتفق بعد إزالة التشكيل وعلامات الترقيم، مع اختلاف في التشكيل أو الترقيم، "
                "والقطعة واحدة ومتصلة وتقع على حد جملة."
            )
        else:
            summary = "حروف النص الموسوم هي حروف المصدر في هذا المدى، والقطعة واحدة ومتصلة وتقع على حد جملة."
    elif diff_sentence:
        extra_reasons = [reason for reason in reasons if reason not in diff_sentence]
        summary = diff_sentence
        if extra_reasons:
            summary = summary + " " + " ".join(extra_reasons)
    else:
        summary = " ".join(reasons) if reasons else "لا فرق حرفي ظاهر في هذا المدى."

    return {
        "color": color,
        "reasons": reasons,
        "summary_ar": summary,
        "diacritics_or_punctuation_differ": diacritics,
        "differences": diffs,
        "gaps": gaps + apparatus,
        "location": {"start": outer_start, "end": outer_end},
        "fragments": [fragment_public(fragment) for fragment in fragments],
        "source_runs": source_runs,
        "ann_runs": ann_runs,
        "leading_elision": leading,
        "trailing_elision": trailing,
    }


def build_system_units(source: str, spans_by_id: dict, tag_doc: dict, layers: list[dict]) -> list[dict]:
    units = []
    for unit in tag_doc["units"]:
        spans = [spans_by_id[span_id] for span_id in unit["span_ids"]]
        mismatches = []
        for span in spans:
            actual = source[span["start"] : span["end"]]
            if actual != span["text"]:
                mismatches.append(span)
        outer_start = spans[0]["start"]
        outer_end = spans[-1]["end"]
        gap_rows = []
        for left, right in zip(spans, spans[1:]):
            if right["start"] <= left["end"]:
                continue
            gap_layers = []
            for row in layers:
                if row["layer"] == "author":
                    continue
                if row["end"] <= left["end"] or row["start"] >= right["start"]:
                    continue
                gap_layers.append(row)
            gap_rows.append((left["end"], right["start"], gap_layers))

        reasons: list[str] = []
        differences = []
        if mismatches:
            for index, span in enumerate(mismatches, start=1):
                actual = source[span["start"] : span["end"]]
                differences.append(
                    {
                        "kind": "variant",
                        "annotation_words": [span["text"]],
                        "source_words": [actual],
                        "annotation_norms": [l1_normalize(span["text"])],
                        "source_norms": [l1_normalize(actual)],
                        "source_start": span["start"],
                        "source_end": span["end"],
                        "annotation_start": 0,
                        "annotation_end": 0,
                        "pair": index,
                    }
                )
            reasons.append("نص وحدة الوسم لا يساوي مقطع المصدر عند الإزاحات المحفوظة.")
            color = "discrepancy"
        else:
            if gap_rows:
                names = []
                for _, _, rows in gap_rows:
                    for row in rows:
                        label = LAYER_AR.get(row["layer"], row["layer"])
                        if label not in names:
                            names.append(label)
                reasons.append(
                    "الوحدة تتخطى مادة غير كلام المؤلف بين أولها وآخرها: " + join_ar(names) + "."
                )
            reasons.extend(sentence_issues(source, outer_start, outer_end))
            color = "highlighted" if reasons else "matched"

        annotated = "".join(span["text"] for span in spans)
        if color == "matched":
            summary = (
                "حروف النص الموسوم هي حروف المصدر في هذا المدى، والوحدة تبدأ وتنتهي على حد جملة، "
                "ولا يقع بينها كلام من غير المؤلف."
            )
        elif color == "discrepancy":
            summary = summary_from_diffs(differences) or "نص الوحدة لا يساوي مقطع المصدر."
        else:
            summary = " ".join(reasons)

        kind = color
        source_runs = []
        offset = 0
        ann_parts = []
        for index, span in enumerate(spans):
            if mismatches and span not in mismatches:
                offset += len(span["text"])
                continue
            if mismatches and span in mismatches:
                pair = mismatches.index(span) + 1
                source_runs.append(
                    {
                        "start": span["start"],
                        "end": span["end"],
                        "kind": "discrepancy",
                        "label": f"discrepancy {pair}",
                        "title": "نص الوحدة لا يساوي مقطع المصدر",
                        "pair": pair,
                    }
                )
                ann_parts.append(
                    {
                        "start": offset,
                        "end": offset + len(span["text"]),
                        "kind": "discrepancy",
                        "label": f"discrepancy {pair}",
                        "title": "نص الوحدة لا يساوي مقطع المصدر",
                        "pair": pair,
                    }
                )
            else:
                source_runs.append(
                    {
                        "start": span["start"],
                        "end": span["end"],
                        "kind": kind,
                        "label": kind,
                        "pair": None,
                    }
                )
                ann_parts.append(
                    {
                        "start": offset,
                        "end": offset + len(span["text"]),
                        "kind": kind,
                        "label": kind,
                        "pair": None,
                    }
                )
            offset += len(span["text"])
        for gap_start, gap_end, rows in gap_rows:
            label = join_ar(
                list(dict.fromkeys(LAYER_AR.get(row["layer"], row["layer"]) for row in rows))
            ) or "حاشية المحقق"
            source_runs.append(
                {
                    "start": gap_start,
                    "end": gap_end,
                    "kind": "apparatus",
                    "label": label,
                    "title": label,
                    "pair": None,
                }
            )

        source_runs = coalesce(source_runs, source)
        ann_runs = coalesce(ann_parts, annotated)
        first_label(source_runs, kind)
        first_label(ann_runs, kind)

        fragments = [fragment_public([word for word in tokenize(annotated, 0) if word["norm"]])]
        units.append(
            {
                "unit_id": unit["unit_id"],
                "text": annotated,
                "span_ids": list(unit["span_ids"]),
                "tags": {
                    "source": tag_objects(unit.get("source_tags") or []),
                    "content": tag_objects(unit.get("content_tags") or []),
                },
                "note_ar": unit.get("reason_ar") or "",
                "note_label_ar": "سبب الوسم عند النظام",
                "confidence": unit.get("confidence"),
                "color": color,
                "reasons": reasons,
                "summary_ar": summary,
                "diacritics_or_punctuation_differ": False,
                "differences": differences,
                "gaps": [
                    {"start": start, "end": end, "role": "apparatus"}
                    for start, end, _rows in gap_rows
                ],
                "location": {"start": outer_start, "end": outer_end},
                "fragments": fragments,
                "source_runs": source_runs,
                "ann_runs": ann_runs,
                "leading_elision": False,
                "trailing_elision": False,
            }
        )
    return units


def build_excel_units(doc: dict, aligner: Aligner) -> list[dict]:
    units = []
    for unit in doc["units"]:
        aligned = align_excel_unit(unit["text"], aligner)
        units.append(
            {
                "unit_id": unit["unit_id"],
                "text": unit["text"],
                "span_ids": [],
                "tags": {
                    "source": plain_tags(unit.get("source_tags_ar") or []),
                    "content": plain_tags(unit.get("content_tags_ar") or []),
                },
                "note_ar": unit.get("note_ar") or "",
                "note_label_ar": "ملاحظة الجدول",
                "confidence": None,
                "book": unit.get("book"),
                "review_status": unit.get("review_status"),
                **aligned,
            }
        )
    return units


def count_colors(units: list[dict]) -> dict[str, int]:
    counts = {"matched": 0, "highlighted": 0, "discrepancy": 0}
    for unit in units:
        counts[unit["color"]] += 1
    return counts


def assert_known_cases(excel_units: list[dict]) -> None:
    by_id = {unit["unit_id"]: unit for unit in excel_units}

    def pairs(unit_id: str):
        found = []
        for diff in by_id[unit_id]["differences"]:
            found.append((diff["kind"], tuple(diff["annotation_norms"]), tuple(diff["source_norms"])))
        return found

    ak1 = pairs("AK-001")
    if ("variant", ("قد",), ("وقد",)) not in ak1:
        raise SystemExit(f"AK-001 did not surface قد/وقد: {ak1}")
    ak7 = pairs("AK-007")
    if ("variant", ("الأسفع",), ("الأسقع",)) not in ak7:
        raise SystemExit(f"AK-007 missing الأسفع/الأسقع: {ak7}")
    if ("variant", ("القرآن",), ("القرن",)) not in ak7:
        raise SystemExit(f"AK-007 missing القرآن/القرن: {ak7}")


def embed_json(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text.replace("<", "\\u003c").replace(">", "\\u003e")


def check_page(path: Path, expected_sha: str) -> int:
    html = path.read_text(encoding="utf-8")
    lowered = html.lower()
    for forbidden in ("<!doctype", "<html", "<head", "<body"):
        if forbidden in lowered:
            raise SystemExit(f"{path.name} contains forbidden markup {forbidden}")
    urls = re.findall(r"https?://[^\s\"'<>]+", html)
    if not urls:
        raise SystemExit("no external font stylesheet found")
    for url in urls:
        if not url.startswith("https://fonts.googleapis.com/"):
            raise SystemExit(f"unexpected external URL: {url}")
    match = re.search(
        r'<script type="application/json" id="data">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        raise SystemExit("missing #data JSON script")
    data = json.loads(match.group(1))
    if data["source"]["sha256"] != expected_sha:
        raise SystemExit("embedded sha256 does not match the verified source hash")
    if "تمت المطابقة" in html:
        raise SystemExit("page claims the text has been reconciled")
    return path.stat().st_size


def print_report(system_units: list[dict], excel_units: list[dict], sha: str, window, html_bytes: int) -> None:
    print(f"sha256 {sha} verified")
    print(f"window {window[0]}:{window[1]} ({window[1] - window[0]} chars)")
    for label, units in ((SET_SYSTEM, system_units), (SET_EXCEL, excel_units)):
        counts = count_colors(units)
        print(f"set {label}")
        print(f"  matched {counts['matched']}")
        print(f"  highlighted {counts['highlighted']}")
        print(f"  discrepancy {counts['discrepancy']}")
        print("  differences:")
        any_diff = False
        for unit in units:
            if unit["color"] != "discrepancy" and not unit["differences"]:
                continue
            if not unit["differences"] and unit["color"] != "discrepancy":
                continue
            if unit["differences"]:
                any_diff = True
                print(f"    {unit['unit_id']} {unit['color']}")
                for diff in unit["differences"]:
                    print(
                        "      - {kind} ann={ann} src={src} @{start}:{end}".format(
                            kind=diff["kind"],
                            ann=diff["annotation_words"],
                            src=diff["source_words"],
                            start=diff["source_start"],
                            end=diff["source_end"],
                        )
                    )
        if not any_diff:
            print("    (none)")
    print("excel units:")
    for unit in excel_units:
        print(f"  {unit['unit_id']} {unit['color']} | {unit['summary_ar']}")
    print(f"html_bytes {html_bytes}")
    print("CHECK ok")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    source, digest = verify_source()
    spans_doc = load_json(ROOT / "data" / "spans_pilot" / f"{WINDOW_KEY}.json")
    layer_doc = load_json(ROOT / "data" / "layers" / f"{WINDOW_KEY}.json")
    tag_doc = load_json(ROOT / "data" / "tags" / "grok" / f"{WINDOW_KEY}.json")
    excel_doc = load_json(ROOT / "data" / "external" / "excel_pilot_2_255.json")

    spans = spans_doc["spans"]
    window_start = min(span["start"] for span in spans)
    window_end = max(span["end"] for span in spans)
    ranges, layer_at = layer_index(layer_doc["ranges"])
    window_layers = []
    for row in ranges:
        if row["end"] <= window_start or row["start"] >= window_end:
            continue
        window_layers.append(
            {
                "start": max(row["start"], window_start),
                "end": min(row["end"], window_end),
                "layer": row["layer"],
            }
        )

    words = tokenize(source[window_start:window_end], window_start, layer_at)
    author = [word for word in words if word["layer"] == "author"]
    aligner = Aligner(source, author, ranges)
    spans_by_id = {span["id"]: span for span in spans}
    system_units = build_system_units(source, spans_by_id, tag_doc, ranges)
    excel_units = build_excel_units(excel_doc, aligner)
    assert_known_cases(excel_units)

    payload = {
        "checkpoint": "B",
        "ayah": "2:255",
        "model_run_at_this_step": "none",
        "new_model_input": False,
        "source": {
            "file": SOURCE_REL,
            "sha256": digest,
            "window_start": window_start,
            "window_end": window_end,
            "next_char": source[window_end] if window_end < len(source) else None,
            "text": source[window_start:window_end],
        },
        "words": [word_public(word, index) for index, word in enumerate(words)],
        "layers": window_layers,
        "sets": [
            {"id": "system", "label_ar": SET_SYSTEM, "units": system_units},
            {"id": "excel", "label_ar": SET_EXCEL, "units": excel_units},
        ],
    }

    web = ROOT / "web"
    web.mkdir(exist_ok=True)
    data_path = web / "reconcile_data.json"
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    template = (ROOT / "src" / "reconcile_template.html").read_text(encoding="utf-8")
    token = "__RECONCILE_JSON__"
    if template.count(token) != 1:
        raise SystemExit("template must contain __RECONCILE_JSON__ exactly once")
    html = template.replace(token, embed_json(payload))
    html_path = web / "reconcile.html"
    html_path.write_text(html, encoding="utf-8")
    html_bytes = check_page(html_path, digest)
    print_report(system_units, excel_units, digest, (window_start, window_end), html_bytes)


if __name__ == "__main__":
    main()
