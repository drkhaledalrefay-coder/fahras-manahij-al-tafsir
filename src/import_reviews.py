"""Import a UI export into <out-root>/<base>/reviews/<reviewer>/<window>.json.

Reuses export_approved validation (schema + pinned-source fidelity). Does not
invent approvals: only records already marked approved (or rejected with
--include-rejected) that pass validation are written.

--out-root is required. Writing under the repo's data/ happens only when the
human passes an explicit out-root that resolves there. See docs/DECISIONS_PROPOSAL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import export_approved as ea  # noqa: E402

# annotation_id: "<tafsir.id>-<window_key>-<move_id>" (window may contain underscores)
ANNOTATION_ID_RE = re.compile(
    r"^(?P<tafsir>[a-z0-9]+(?:[_-][a-z0-9]+)*)-(?P<window>.+)-(?P<move>[A-Za-z0-9_]+)$"
)
REVIEWER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def window_key_for(record: dict) -> str | None:
    """Derive the reviews/<window>.json stem from annotation_id."""
    aid = record.get("annotation_id")
    if not isinstance(aid, str):
        return None
    match = ANNOTATION_ID_RE.match(aid)
    if match is None:
        return None
    return match.group("window")


def validate_reviewer(name: str) -> str:
    if not REVIEWER_RE.match(name):
        raise ValueError(
            "reviewer must be 1–64 chars: letters, digits, _ . - "
            f"(got {name!r})"
        )
    return name


def select_and_validate(
    records: list[dict],
    *,
    include_rejected: bool = False,
    schema_path: Path = ea.SCHEMA_PATH,
) -> tuple[list[dict], dict]:
    """Return (verified_records, report) using export_approved gates."""
    validator = ea.load_validator(Path(schema_path))
    report: dict = {
        "input": len(records),
        "selected": 0,
        "skipped": 0,
        "kept": 0,
        "dropped_schema": 0,
        "dropped_fidelity": 0,
        "duplicates": 0,
        "dropped": [],
        "by_window": {},
    }
    verified: list[dict] = []
    for record in records:
        if not ea.is_selected(record, include_rejected):
            report["skipped"] += 1
            continue
        report["selected"] += 1
        problems = ea.schema_errors(validator, record)
        if problems:
            report["dropped_schema"] += 1
            report["dropped"].append(
                {
                    "annotation_id": ea.annotation_id_of(record),
                    "stage": "schema",
                    "reason": "; ".join(problems),
                }
            )
            continue
        problems = ea.fidelity_errors(record)
        if problems:
            report["dropped_fidelity"] += 1
            report["dropped"].append(
                {
                    "annotation_id": ea.annotation_id_of(record),
                    "stage": "fidelity",
                    "reason": "; ".join(problems),
                }
            )
            continue
        verified.append(record)

    kept, duplicates = ea.dedupe_by_annotation_id(verified)
    report["duplicates"] = len(duplicates)
    report["dropped"].extend(duplicates)
    report["kept"] = len(kept)
    return kept, report


def group_by_window(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        key = window_key_for(record)
        if key is None:
            raise ValueError(
                f"cannot derive window from annotation_id={record.get('annotation_id')!r}"
            )
        grouped[key].append(record)
    return dict(grouped)


def write_reviews(
    records: list[dict],
    *,
    base: Path,
    reviewer: str,
    out_root: Path,
) -> list[Path]:
    """Write one JSON array per window under <out_root>/<base>/reviews/<reviewer>/."""
    reviewer = validate_reviewer(reviewer)
    base_path = Path(base)
    if base_path.is_absolute():
        raise ValueError("--base must be a repo-relative path like data/v2")
    reviews_dir = out_root / base_path / "reviews" / reviewer

    written: list[Path] = []
    for window, items in sorted(group_by_window(records).items()):
        ordered = sorted(
            items,
            key=lambda r: (
                r["quran"]["surah"],
                r["quran"]["ayah"],
                r["source"]["start_char"],
            ),
        )
        path = reviews_dir / f"{window}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            json.dumps(ordered, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        )
        written.append(path)
    return written


def import_reviews(
    input_path: Path,
    *,
    base: str | Path,
    reviewer: str,
    out_root: Path,
    include_rejected: bool = False,
    schema_path: Path = ea.SCHEMA_PATH,
    allow_version_mismatch: bool = False,
    fahras_path: Path | None = None,
) -> dict:
    if out_root is None:
        raise ValueError("--out-root is required; refusing to default to the repo root")
    root = Path(out_root)
    # Same envelope forms as export_approved (incl. classic UI {data_version, records}).
    records = ea.load_records(
        Path(input_path),
        allow_version_mismatch=allow_version_mismatch,
        fahras_path=fahras_path,
    )
    kept, report = select_and_validate(
        records, include_rejected=include_rejected, schema_path=schema_path
    )
    paths = write_reviews(kept, base=Path(base), reviewer=reviewer, out_root=root)
    report["out_root"] = root.as_posix()
    report["base"] = str(base)
    report["reviewer"] = reviewer
    report["written_paths"] = [p.as_posix() for p in paths]
    report["by_window"] = {
        Path(p).stem: True for p in report["written_paths"]
    }
    return report


def print_summary(report: dict) -> None:
    print(f"عدد المدخل: {report['input']}")
    print(f"المختار للفحص: {report['selected']}")
    print(f"المكتوب بعد التحقق: {report['kept']}")
    print(f"المرفوض (مخطط): {report['dropped_schema']}")
    print(f"المرفوض (مطابقة): {report['dropped_fidelity']}")
    print(f"المكرر: {report['duplicates']}")
    print(f"غير معتمد (تخطّي): {report['skipped']}")
    for path in report.get("written_paths") or []:
        print(f"كتب: {path}")
    if report.get("dropped"):
        for entry in report["dropped"]:
            print(f"  - [{entry['stage']}] {entry['annotation_id']}: {entry['reason']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="import_reviews.py",
        description="استيراد تصدير الواجهة إلى reviews/<reviewer>/<window>.json بعد التحقق.",
    )
    p.add_argument("input", type=Path, help="ملف JSON من زر التصدير في الواجهة")
    p.add_argument(
        "--base",
        required=True,
        help="أساس البيانات النسبي، مثال: data/v2 أو data/multi/al_tabari",
    )
    p.add_argument(
        "--reviewer",
        required=True,
        help="معرّف المراجع البشري (اسم مجلد تحت reviews/)",
    )
    p.add_argument(
        "--out-root",
        type=Path,
        required=True,
        help="جذر الكتابة المطلوب (مثال: مجلد مؤقت، أو جذر المستودع عند الاستيراد الحقيقي).",
    )
    p.add_argument(
        "--include-rejected",
        action="store_true",
        help="أدرج السجلات ذات review.status=rejected كما في export_approved",
    )
    p.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="تجاوز فحص data_version (غير افتراضي؛ للطوارئ/الاختبار فقط)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    try:
        report = import_reviews(
            args.input,
            base=args.base,
            reviewer=args.reviewer,
            out_root=args.out_root,
            include_rejected=args.include_rejected,
            allow_version_mismatch=args.allow_version_mismatch,
        )
    except ea.VersionMismatchError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"فشل الاستيراد: {exc}", file=sys.stderr)
        return 1
    print_summary(report)
    # Empty records → kept=0, selected=0 → exit 0.
    return 0 if report["kept"] or report["selected"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
