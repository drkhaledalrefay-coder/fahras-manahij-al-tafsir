"""Export the annotations a specialist approved into a verified approved.json.

Deterministic and offline: no AI, no network, standard library + jsonschema only.

Usage:
    python src/export_approved.py INPUT.json --out approved.json [--include-rejected]

INPUT is what the review UI's «تصدير المعتمد» button copies: a JSON array of
records, an object with "annotations", an object with "records" (classic UI:
optional data_version), or one record. Every selected record is validated
against schema/annotation.schema.json (draft 2020-12) and then re-verified against the
pinned source file (source.sha256, text == source[start_char:end_char], end > start);
records that fail are reported with a reason and are never written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "annotation.schema.json"
FAHRAS_HTML = ROOT / "web" / "fahras.html"
# Same compact JSON form as build_fahras.embed() / _stable_build_date.
DATA_VERSION_RE = re.compile(r'"data_version":"([^"]+)"')
VERSION_MISMATCH_MSG = "نسخة البيانات مختلفة — أعد التحقق من القرارات"

APPROVED = "approved"
REJECTED = "rejected"
# Working states: never publishable, not even with --include-rejected.
WORKING_STATUSES = ("ai_proposed", "under_review")


class VersionMismatchError(ValueError):
    """UI export data_version does not match the current build."""

    def __init__(self, message: str = VERSION_MISMATCH_MSG) -> None:
        super().__init__(message)


def current_data_version(html_path: Path | None = None) -> str:
    """Read data_version embedded in web/fahras.html (build_fahras output)."""
    path = Path(html_path) if html_path is not None else FAHRAS_HTML
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError as exc:
        raise ValueError(f"تعذّر قراءة data_version من البناء الحالي: {exc}") from exc
    match = DATA_VERSION_RE.search(text)
    if match is None:
        raise ValueError(f"تعذّر قراءة data_version من البناء الحالي: {path.as_posix()}")
    return match.group(1)

# --- one place to teach the tool about another tafsir or dataset -------------------
# tafsir.id -> directory holding that work's pinned "<surah>_<ayah>.txt" files.
# Everything pinned today is extracted from the Tafsir Center database, so a single
# "default" entry covers it; a second source only adds one entry to this table.
TAFSIR_SOURCE_DIRS: dict[str, Path] = {
    "default": ROOT / "data" / "raw" / "tafsircenter",
}

SOURCE_ID_RE = re.compile(
    r"^(?P<tafsir>[a-z0-9]+(?:[_-][a-z0-9]+)*)_(?P<surah>\d{1,3})_(?P<ayah>\d{1,3})$"
)


def source_file_for(source_id: str) -> Path | None:
    """Map source.source_id "<tafsir_id>_<surah>_<ayah>" to its pinned text file.

    Returns None when the id does not follow the convention; callers treat that as a
    fidelity failure. This is the only mapping in the tool: adding another tafsir
    (or another dataset) means adding one entry to TAFSIR_SOURCE_DIRS.
    """
    match = SOURCE_ID_RE.match(source_id or "")
    if match is None:
        return None
    directory = TAFSIR_SOURCE_DIRS.get(match.group("tafsir"), TAFSIR_SOURCE_DIRS["default"])
    return directory / f"{match.group('surah')}_{match.group('ayah')}.txt"


def review_status(record: dict) -> str | None:
    review = record.get("review")
    if isinstance(review, dict):
        status = review.get("status")
        if isinstance(status, str):
            return status
    return None


def is_selected(record: dict, include_rejected: bool) -> bool:
    """Only "approved" is publishable; "rejected" joins it on request.

    ai_proposed and under_review are working states and are never selected.
    """
    status = review_status(record)
    if status in WORKING_STATUSES:
        return False
    if status == APPROVED:
        return True
    return bool(include_rejected and status == REJECTED)


def annotation_id_of(record: dict) -> str:
    value = record.get("annotation_id")
    return value if isinstance(value, str) and value else "<no annotation_id>"


def load_records(
    path: Path,
    *,
    allow_version_mismatch: bool = False,
    fahras_path: Path | None = None,
) -> list[dict]:
    """Load a UI export.

    Accepted shapes:
      - JSON array of records
      - object with "records" (classic fahras «تصدير كل المعتمد»)
      - object with "annotations"
      - a single record object

    When the envelope carries data_version, it must match the current build
    (web/fahras.html) unless allow_version_mismatch is True.
    """
    payload = json.loads(path.read_bytes().decode("utf-8"))
    envelope_version: object | None = None
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
        records = payload["records"]
        if "data_version" in payload:
            envelope_version = payload["data_version"]
    elif isinstance(payload, dict) and isinstance(payload.get("annotations"), list):
        records = payload["annotations"]
        if "data_version" in payload:
            envelope_version = payload["data_version"]
    elif isinstance(payload, dict) and "annotation_id" in payload:
        records = [payload]
    else:
        raise ValueError(
            'input must be a JSON array of records, an object with a "records" '
            'or "annotations" array, or a single record object'
        )
    if envelope_version is not None and not allow_version_mismatch:
        current = current_data_version(fahras_path)
        if str(envelope_version) != current:
            raise VersionMismatchError()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record #{index} is not a JSON object")
    return records


def load_validator(schema_path: Path = SCHEMA_PATH) -> jsonschema.Draft202012Validator:
    schema = json.loads(schema_path.read_bytes().decode("utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    # Format assertions stay off on purpose: the schema carries an explicit pattern
    # for every date-time field, so the result is identical on every machine.
    return jsonschema.Draft202012Validator(schema)


def schema_errors(validator: jsonschema.Draft202012Validator, record: dict) -> list[str]:
    errors = sorted(
        validator.iter_errors(record),
        key=lambda error: (str(list(error.absolute_path)), error.message),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<record>'}: {error.message}"
        for error in errors
    ]


def fidelity_errors(record: dict) -> list[str]:
    """Re-verify the record against the pinned source file, independent of the UI.

    The source text is never trusted from the record: the pinned file is re-hashed
    and the recorded offsets are re-sliced. Reading is UTF-8 with newline="" so no
    \\r is translated and no offset shifts.
    """
    source = record["source"]
    path = source_file_for(source["source_id"])
    if path is None:
        return [f"source_id لا يتبع الصيغة <tafsir_id>_<surah>_<ayah>: {source['source_id']!r}"]
    if not path.is_file():
        return [f"ملف المصدر المثبّت غير موجود: {path.as_posix()}"]
    if source["end_char"] <= source["start_char"]:
        return [
            "حدود الموضع غير صحيحة: end_char "
            f"{source['end_char']} ليس أكبر من start_char {source['start_char']}"
        ]

    with open(path, "rb") as handle:
        raw = handle.read()
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()

    reasons: list[str] = []
    if source["sha256"] is not None:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source["sha256"]:
            reasons.append(f"بصمة ملف المصدر لا تساوي source.sha256 (المحسوبة {digest})")
    if text[source["start_char"] : source["end_char"]] != record["text"]:
        reasons.append("text لا يساوي source[start_char:end_char] حرفاً بحرف")
    return reasons


def _reviewed_at_key(record: dict) -> tuple[float, str]:
    """Sortable key for review.reviewed_at; unparseable values sort lowest."""
    review = record.get("review")
    reviewed_at = review.get("reviewed_at") if isinstance(review, dict) else None
    if not isinstance(reviewed_at, str) or not reviewed_at:
        return (float("-inf"), "")
    try:
        stamp = datetime.fromisoformat(reviewed_at.replace("z", "Z").replace("Z", "+00:00"))
    except ValueError:
        return (float("-inf"), reviewed_at)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (stamp.timestamp(), reviewed_at)


def dedupe_by_annotation_id(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep one record per annotation_id: the latest review.reviewed_at.

    Ties (and unparseable timestamps) keep the first occurrence seen, so the result
    never depends on anything but the input order. Returns (kept, dropped).
    """
    kept: list[dict] = []
    position_of: dict[str, int] = {}
    dropped: list[dict] = []
    for record in records:
        key = annotation_id_of(record)
        position = position_of.get(key)
        if position is None:
            position_of[key] = len(kept)
            kept.append(record)
            continue
        if _reviewed_at_key(record) > _reviewed_at_key(kept[position]):
            dropped.append(
                {
                    "annotation_id": key,
                    "stage": "duplicate",
                    "reason": "نسخة مكررة أقدم: حُفظت نسخة أحدث في review.reviewed_at",
                }
            )
            kept[position] = record
        else:
            dropped.append(
                {
                    "annotation_id": key,
                    "stage": "duplicate",
                    "reason": "نسخة مكررة أقدم أو مساوية لنسخة محفوظة في review.reviewed_at",
                }
            )
    return kept, dropped


def write_approved(records: list[dict], out_path: Path) -> list[dict]:
    """Write the approved array (UTF-8, ensure_ascii=False, indent 2); return it."""
    ordered = sorted(
        records,
        key=lambda record: (
            record["quran"]["surah"],
            record["quran"]["ayah"],
            record["source"]["start_char"],
        ),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(json.dumps(ordered, ensure_ascii=False, indent=2).encode("utf-8"))
    return ordered


def export(
    input_path: Path,
    out_path: Path,
    include_rejected: bool = False,
    schema_path: Path = SCHEMA_PATH,
    *,
    allow_version_mismatch: bool = False,
    fahras_path: Path | None = None,
) -> dict:
    """Run the whole export and return a report dict (also the source of the summary)."""
    records = load_records(
        Path(input_path),
        allow_version_mismatch=allow_version_mismatch,
        fahras_path=fahras_path,
    )
    validator = load_validator(Path(schema_path))
    report: dict = {
        "input": len(records),
        "selected": 0,
        "skipped": 0,
        "written": 0,
        "written_approved": 0,
        "written_rejected": 0,
        "dropped_schema": 0,
        "dropped_fidelity": 0,
        "duplicates": 0,
        "dropped": [],
        "written_ids": [],
        "out": Path(out_path).as_posix(),
    }

    verified: list[dict] = []
    for record in records:
        if not is_selected(record, include_rejected):
            report["skipped"] += 1
            continue
        report["selected"] += 1
        problems = schema_errors(validator, record)
        if problems:
            report["dropped_schema"] += 1
            report["dropped"].append(
                {
                    "annotation_id": annotation_id_of(record),
                    "stage": "schema",
                    "reason": "; ".join(problems),
                }
            )
            continue
        problems = fidelity_errors(record)
        if problems:
            report["dropped_fidelity"] += 1
            report["dropped"].append(
                {
                    "annotation_id": annotation_id_of(record),
                    "stage": "fidelity",
                    "reason": "; ".join(problems),
                }
            )
            continue
        verified.append(record)

    kept, duplicates = dedupe_by_annotation_id(verified)
    report["duplicates"] = len(duplicates)
    report["dropped"].extend(duplicates)

    ordered = write_approved(kept, Path(out_path))
    report["written"] = len(ordered)
    report["written_ids"] = [record["annotation_id"] for record in ordered]
    report["written_approved"] = sum(1 for r in ordered if review_status(r) == APPROVED)
    report["written_rejected"] = sum(1 for r in ordered if review_status(r) == REJECTED)
    return report


def print_summary(report: dict, include_rejected: bool = False) -> None:
    """Arabic summary of the export: what was written, what was dropped and why."""
    print(f"عدد المدخل: {report['input']}")
    print(f"المعتمد المكتوب: {report['written']}")
    print(f"المرفوض بسبب المخطط: {report['dropped_schema']}")
    print(f"المرفوض بسبب عدم المطابقة: {report['dropped_fidelity']}")
    print(f"المكرر: {report['duplicates']}")
    print(f"غير معتمد (لم يُفحص ولم يُكتب): {report['skipped']}")
    if include_rejected:
        print(f"منها مرفوضة أُدرجت بـ --include-rejected: {report['written_rejected']}")
    if report["dropped"]:
        labels = {"schema": "المخطط", "fidelity": "عدم المطابقة", "duplicate": "مكرر"}
        print("تفاصيل المرفوض:")
        for entry in report["dropped"]:
            stage = labels.get(entry["stage"], entry["stage"])
            print(f"  - [{stage}] {entry['annotation_id']}: {entry['reason']}")
    print(f"ملف الخرج: {report['out']}")


def _enable_utf8_stdout() -> None:
    """Keep the Arabic summary printable on consoles with a legacy code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_approved.py",
        description="تصدير الوسوم المعتمدة في واجهة المراجعة إلى approved.json موثَّق.",
    )
    parser.add_argument(
        "input",
        help=(
            "ملف JSON من زر «تصدير المعتمد» "
            "(مصفوفة، أو كائن فيه records/annotations، أو سجل واحد)"
        ),
    )
    parser.add_argument("--out", required=True, help="ملف الخرج: مصفوفة السجلات المعتمدة")
    parser.add_argument(
        "--include-rejected",
        action="store_true",
        help="أدرج rejected أيضاً؛ ai_proposed و under_review لا يُصدَّران أبداً",
    )
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="تجاوز فحص data_version (غير افتراضي؛ للطوارئ/الاختبار فقط)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _enable_utf8_stdout()
    args = build_parser().parse_args(argv)
    try:
        report = export(
            Path(args.input),
            Path(args.out),
            include_rejected=args.include_rejected,
            allow_version_mismatch=args.allow_version_mismatch,
        )
    except FileNotFoundError as exc:
        print(f"خطأ: الملف غير موجود: {exc.filename}")
        return 2
    except json.JSONDecodeError as exc:
        print(f"خطأ: ملف JSON غير صالح: {exc}")
        return 2
    except VersionMismatchError as exc:
        print(str(exc))
        return 2
    except (ValueError, jsonschema.exceptions.SchemaError) as exc:
        print(f"خطأ: {exc}")
        return 2
    except OSError as exc:
        print(f"خطأ: تعذّر قراءة المدخل: {exc}")
        return 2
    print_summary(report, include_rejected=args.include_rejected)
    # Empty records → written=[], dropped=0 → exit 0 (nothing to approve, nothing failed).
    dropped = report["dropped_schema"] + report["dropped_fidelity"] + report["duplicates"]
    return 1 if dropped else 0


if __name__ == "__main__":
    raise SystemExit(main())
