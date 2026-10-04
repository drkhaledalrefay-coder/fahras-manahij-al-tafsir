"""CLI: classify one window via API or manual paste, then run strict verifier.

Examples:
  python src/run_window.py --tafsir al_tabari --window 2_102 --dry-run
  python src/run_window.py --tafsir al_tabari --window 2_102 --api
  python src/run_window.py --tafsir al_tabari --window 2_102 --manual-out prompt.txt
  python src/run_window.py --tafsir al_tabari --window 2_102 --manual-in reply.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import classify_api  # noqa: E402
import grounding_contract  # noqa: E402
from v2_verify import configure, verify_window  # noqa: E402

TAFSIR_BASES = {
    "ibn_kathir": "data/v2",
    "v2": "data/v2",
    "al_tabari": "data/multi/al_tabari",
    "al_baghawi": "data/multi/al_baghawi",
    "al_saadi": "data/multi/al_saadi",
}


def _format_path(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def resolve_base(tafsir: str | None, base: str | Path | None = None) -> Path:
    if base is not None:
        p = Path(base)
        if p.is_absolute():
            return p.resolve()
        if (ROOT / p).exists() or not (Path.cwd() / p).exists():
            return (ROOT / p).resolve()
        return (Path.cwd() / p).resolve()
    key = (tafsir or "").strip()
    if key in TAFSIR_BASES:
        return ROOT / TAFSIR_BASES[key]
    # Allow data/multi/<name> style ids
    multi = ROOT / "data" / "multi" / key
    if multi.is_dir():
        return multi
    raise SystemExit(f"unknown tafsir {tafsir!r}; choose: {', '.join(sorted(TAFSIR_BASES))}")


def packet_path_for(base: Path, window: str) -> Path:
    path = base / "packets" / f"{window}.json"
    if not path.is_file():
        raise SystemExit(f"packet not found: {_format_path(path)}")
    return path


def validate_packet(packet: dict) -> None:
    if not packet.get("window_id"):
        raise SystemExit("packet missing window_id")
    spans = packet.get("spans") or []
    if not spans:
        raise SystemExit("packet has no spans")
    ids = [s.get("id") for s in spans if isinstance(s, dict)]
    if len(ids) != len(set(ids)):
        raise SystemExit("packet has duplicate span ids")


def write_manual_prompt(packet: dict, out_file: Path) -> Path:
    body = classify_api.build_user_prompt(packet)
    header = (
        "# مصنّف منهجية التفسير — الصق هذا الملف كاملاً في أي محادثة "
        "(ChatGPT / Claude / Gemini)\n"
        "# تنبيه: أي رد يدوي يُلصق هنا يُعامل كمدخل غير مضمون (unverified input) "
        "ولا يُرشّح أبداً للاعتماد الآلي بل يحال للمتخصص فقط.\n"
        "# Note: Any manual reply pasted back is treated as unverified input "
        "and will never be nominated for auto-candidate (specialist review only).\n"
        "# أعد كائن JSON فقط (window + moves). لا تنسخ نص المصدر.\n\n"
    )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_bytes((header + body).encode("utf-8"))
    return out_file


def load_manual_reply(path: Path) -> dict:
    raw = path.read_bytes().decode("utf-8")
    return classify_api.extract_json_object(raw)


def run_verifier(base: Path, annotator: str, window_id: str, moves_payload: dict) -> dict:
    configure(base)
    result = verify_window(annotator, window_id, moves_payload)
    verified_dir = base / "verified" / annotator
    verified_dir.mkdir(parents=True, exist_ok=True)
    out = verified_dir / f"{window_id}.json"
    out.write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    summary = result["summary"]
    print(
        f"verifier: moves={summary['move_count']} "
        f"auto={summary['auto_candidate']} "
        f"specialist={summary['specialist']} "
        f"flags={summary['flag_count']}"
    )
    return result


def _run_verifier_or_fail(
    base: Path, annotator: str, window_id: str, moves_payload: dict
) -> int:
    """Run verifier; on any exception print structured RUN_FAILURE and return 1."""
    try:
        run_verifier(base, annotator, window_id, moves_payload)
        return 0
    except Exception as e:
        rec = classify_api.make_failure_record(window_id, "RUN_FAILURE", str(e))
        print(json.dumps(rec, ensure_ascii=False))
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Classify one tafsir window (API or manual) and verify."
    )
    p.add_argument("--tafsir", default=None, help="al_tabari | al_baghawi | al_saadi | ibn_kathir")
    p.add_argument("--base", default=None, help="base directory (e.g. data/anfal/al_tabari)")
    p.add_argument("--window", required=True, help="window id, e.g. 2_102")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--api", action="store_true", help="call OpenAI-compatible endpoint")
    mode.add_argument(
        "--manual-out",
        metavar="FILE",
        help="write a self-contained prompt file for pasting into any chat",
    )
    mode.add_argument(
        "--manual-in",
        metavar="FILE",
        help="read pasted JSON reply and save under moves/manual_<date>/",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="validate packet and print what would be sent; no network",
    )
    p.add_argument("--model", default=None, help="override LLM_MODEL")
    p.add_argument("--base-url", default=None, help="override LLM_BASE_URL")
    args = p.parse_args(argv)
    if not args.tafsir and not args.base:
        p.error("either --tafsir or --base is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base = resolve_base(args.tafsir, base=args.base)
    pkt_path = packet_path_for(base, args.window)
    packet = classify_api.load_packet(pkt_path)
    validate_packet(packet)
    window_id = str(packet.get("window_id") or args.window)
    moves_dir = base / "moves"

    if args.dry_run and not args.api and not args.manual_out and not args.manual_in:
        messages = classify_api.build_messages(packet)
        print(f"packet: {_format_path(pkt_path)}")
        print(f"window: {window_id}")
        print(f"spans: {len(packet.get('spans') or [])}")
        print(f"base: {_format_path(base)}")
        print("--- would send (system) ---")
        print(messages[0]["content"][:500])
        print("--- would send (user, first 1500 chars) ---")
        print(messages[1]["content"][:1500])
        if len(messages[1]["content"]) > 1500:
            print(f"... [{len(messages[1]['content'])} chars total]")
        print("dry-run: no network call")
        return 0

    if args.manual_out:
        out = Path(args.manual_out)
        if not out.is_absolute():
            out = Path.cwd() / out
        path = write_manual_prompt(packet, out)
        print(f"wrote manual prompt: {_format_path(path)}")
        if args.dry_run:
            print("dry-run: prompt written; no network; no verifier")
        return 0

    if args.manual_in:
        reply_path = Path(args.manual_in)
        if not reply_path.is_absolute():
            reply_path = Path.cwd() / reply_path
        if not reply_path.is_file():
            raise SystemExit(f"manual-in file not found: {reply_path}")
        try:
            payload = load_manual_reply(reply_path)
        except classify_api.ClassifyError as e:
            rec = classify_api.make_failure_record(window_id, "MODEL_OUTPUT_INVALID", str(e))
            print(json.dumps(rec, ensure_ascii=False))
            return 1
        errors = classify_api.validate_span_ids(packet, payload)
        if errors:
            rec = classify_api.make_failure_record(
                window_id, "MODEL_OUTPUT_INVALID", "invalid span ids: " + "; ".join(errors[:8])
            )
            print(json.dumps(rec, ensure_ascii=False))
            return 1
        annotator = f"manual_{date.today().isoformat()}"
        cleaned = classify_api.sanitize_moves_payload(payload, window_id)
        cleaned[grounding_contract.INPUT_ASSURANCE_FIELD] = (
            grounding_contract.INPUT_MANUAL_UNVERIFIED
        )
        cleaned[grounding_contract.PACKET_SHA_FIELD] = None
        path = classify_api.write_moves(moves_dir, annotator, window_id, cleaned)
        print(
            "مدخل يدوي غير مضمون — لا يُرشّح للاعتماد الآلي، مراجعة متخصصة فقط | "
            "manual reply = unverified input, never nominated, specialist review only"
        )
        print(f"wrote moves: {_format_path(path)}")
        return _run_verifier_or_fail(base, annotator, window_id, cleaned)

    if args.api:
        model, base_url = classify_api.resolve_env(model=args.model, base_url=args.base_url)
        if not model:
            raise SystemExit("set LLM_MODEL or pass --model")
        if not base_url and not args.dry_run:
            raise SystemExit("set LLM_BASE_URL or pass --base-url")
        if args.dry_run:
            result = classify_api.classify(
                pkt_path, model, base_url or "(unset)", moves_dir, dry_run=True
            )
            print(f"packet: {_format_path(pkt_path)}")
            print(f"model: {result['model']} → annotator={result['annotator']}")
            print(f"base_url: {base_url or '(unset)'}")
            print("--- would send (user, first 1500 chars) ---")
            print(result["messages"][1]["content"][:1500])
            print("dry-run: no network call")
            return 0
        try:
            result = classify_api.classify(pkt_path, model, base_url, moves_dir)
        except classify_api.ClassifyError as e:
            rec = getattr(e, "record", None) or classify_api.make_failure_record(
                window_id, "RUN_FAILURE", str(e)
            )
            print(json.dumps(rec, ensure_ascii=False))
            return 1
        if isinstance(result, dict) and result.get("status") == "failed":
            print(json.dumps(result, ensure_ascii=False))
            return 1
        path = result["path"]
        print(f"wrote moves: {_format_path(path)}")
        return _run_verifier_or_fail(base, result["annotator"], window_id, result["payload"])

    # No mode: default to dry-run-style packet check
    print(f"packet ok: {_format_path(pkt_path)} ({len(packet.get('spans') or [])} spans)")
    print("pass --api, --manual-out FILE, --manual-in FILE, or --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
