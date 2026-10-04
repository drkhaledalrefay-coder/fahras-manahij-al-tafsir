"""OpenAI-compatible chat adapter: packet → moves JSON (span IDs only).

API key from LLM_API_KEY only. Never copies model text into source fields.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import grounding_contract

MOVE_FIELDS = (
    "move_id",
    "span_ids",
    "primary",
    "secondary",
    "content_tags",
    "certainty",
    "evidence_span_ids",
    "author_verdict_span_ids",
    "references",
    "alternatives",
    "rationale_ar",
)

SPAN_ID_KEYS = ("span_ids", "evidence_span_ids", "author_verdict_span_ids")

HttpPost = Callable[[str, dict[str, str], bytes], bytes]


def make_failure_record(window_id: str, reason_code: str, error: str) -> dict[str, str]:
    return {
        "window_id": str(window_id),
        "status": "failed",
        "reason_code": str(reason_code),
        "error": str(error)[:200],
    }


class ClassifyError(Exception):
    """Classification failed after validation / retries."""

    def __init__(
        self,
        message: str,
        *,
        record: dict[str, Any] | None = None,
        reason_code: str = "RUN_FAILURE",
        window_id: str | None = None,
    ) -> None:
        super().__init__(message)
        if record is not None:
            self.record = record
        else:
            self.record = make_failure_record(window_id or "", reason_code, message)

    def __getitem__(self, item: str) -> Any:
        return self.record[item]

    def get(self, item: str, default: Any = None) -> Any:
        return self.record.get(item, default)


def model_slug(model: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (model or "model").strip()).strip("_").lower()
    return slug or "model"


def load_packet(packet_path: Path | str) -> dict:
    path = Path(packet_path)
    return json.loads(path.read_bytes().decode("utf-8"))


def packet_span_ids(packet: dict) -> set[str]:
    return {s["id"] for s in (packet.get("spans") or []) if isinstance(s, dict) and "id" in s}


def extract_json_object(text: str) -> dict:
    """Parse a JSON object from model text (raw or fenced)."""
    raw = (text or "").strip()
    if not raw:
        raise ClassifyError("empty model reply", reason_code="MODEL_OUTPUT_INVALID")
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise ClassifyError("model reply is not a JSON object", reason_code="MODEL_OUTPUT_INVALID")


def validate_span_ids(packet: dict, payload: dict) -> list[str]:
    """Return error messages for unknown span ids (empty list = ok)."""
    known = packet_span_ids(packet)
    errors: list[str] = []
    moves = payload.get("moves")
    if not isinstance(moves, list):
        return ["moves must be a list"]
    for i, move in enumerate(moves):
        if not isinstance(move, dict):
            errors.append(f"move[{i}] is not an object")
            continue
        for key in SPAN_ID_KEYS:
            ids = move.get(key) or []
            if not isinstance(ids, list):
                errors.append(f"move[{i}].{key} must be a list")
                continue
            for sid in ids:
                if sid not in known:
                    errors.append(f"unknown span id {sid!r} in move[{i}].{key}")
    return errors


def sanitize_moves_payload(payload: dict, window_id: str) -> dict:
    """Keep moves schema fields only — never store model text as source."""
    cleaned_moves: list[dict] = []
    for move in payload.get("moves") or []:
        if not isinstance(move, dict):
            continue
        out: dict[str, Any] = {}
        for key in MOVE_FIELDS:
            if key not in move:
                continue
            val = move[key]
            if key == "references" and isinstance(val, dict):
                out[key] = {
                    "verses": list(val.get("verses") or []),
                    "hadith": list(val.get("hadith") or []),
                    "persons": list(val.get("persons") or []),
                }
            elif key in SPAN_ID_KEYS:
                out[key] = [str(x) for x in (val or [])]
            elif key in ("secondary", "content_tags", "alternatives"):
                out[key] = list(val or [])
            else:
                out[key] = val
        # Defaults so file matches existing moves shape
        out.setdefault("span_ids", [])
        out.setdefault("secondary", [])
        out.setdefault("content_tags", [])
        out.setdefault("evidence_span_ids", [])
        out.setdefault("author_verdict_span_ids", [])
        out.setdefault("references", {"verses": [], "hadith": [], "persons": []})
        out.setdefault("alternatives", [])
        # Drop any accidental source/text fields from the model
        cleaned_moves.append(out)
    return {"window": window_id, "moves": cleaned_moves}


def build_user_prompt(packet: dict, error_feedback: str | None = None) -> str:
    """Self-contained prompt: instructions + numbered spans + required schema."""
    lines: list[str] = []
    lines.append(packet.get("instructions_ar") or "أعد JSON فقط. معرّفات spans دون نص.")
    lines.append("")
    lines.append(f"window_id: {packet.get('window_id')}")
    lines.append(f"ayah: {packet.get('ayah')}")
    h = grounding_contract.packet_sha256(packet)
    lines.append(f"packet_sha256: {h}")
    lines.append("")
    lines.append("## التعريفات")
    lines.append(json.dumps(packet.get("definitions") or [], ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("## قواعد اليقين")
    lines.append(json.dumps(packet.get("certainty_rules") or {}, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("## مخطط الإخراج المطلوب (JSON فقط)")
    schema = copy.deepcopy(
        packet.get("output_schema")
        or {
            "window": "<window_id>",
            "moves": [
                {
                    "move_id": "m01",
                    "span_ids": ["s001"],
                    "primary": "M_RAY",
                    "secondary": [],
                    "content_tags": [],
                    "certainty": "strong",
                    "evidence_span_ids": ["s001"],
                    "author_verdict_span_ids": [],
                    "references": {"verses": [], "hadith": [], "persons": []},
                    "alternatives": [],
                    "rationale_ar": "ملاحظة غير مُسنَدة — لا تُعرض دليلاً",
                }
            ],
        }
    )
    if isinstance(schema, dict) and isinstance(schema.get("moves"), list):
        for m in schema["moves"]:
            if isinstance(m, dict) and "rationale_ar" in m:
                m["rationale_ar"] = "ملاحظة غير مُسنَدة — لا تُعرض دليلاً"
    lines.append(json.dumps(schema, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("أعد كائن JSON فقط بالحقلين window و moves.")
    lines.append("لا تنسخ نص المصدر؛ أعد معرّفات spans والوسوم واليقين فقط.")
    lines.append("حقل rationale_ar اختياري: ملاحظة غير مُسنَدة — لا تُعرض دليلاً.")
    lines.append(
        "كل مرجع في references (آيات verses أو أحاديث hadith أو أعلام persons) "
        "يجب أن يسنده معرّف شاهد في evidence_span_ids."
    )
    lines.append("")
    lines.append("## الأجزاء المرقّمة (spans)")
    for span in packet.get("spans") or []:
        sid = span.get("id")
        text = span.get("text") or ""
        markers = span.get("markers") or []
        marker_note = ""
        if markers:
            families = ",".join(
                str(m.get("family") or m.get("marker") or "?") for m in markers
            )
            marker_note = f" [markers:{families}]"
        lines.append(f"{sid}:{marker_note} {text}")
    if packet.get("editor_footnote_evidence"):
        lines.append("")
        lines.append("## حاشية المحقق (ليست كلام المفسّر)")
        lines.append(
            json.dumps(
                packet.get("editor_footnote_evidence"),
                ensure_ascii=False,
                indent=2,
            )
        )
    if error_feedback:
        lines.append("")
        lines.append("## تصحيح مطلوب")
        lines.append(error_feedback)
        lines.append("أعد JSON صالحاً بمعرّفات spans موجودة في الحزمة فقط.")
    return "\n".join(lines)


def build_messages(packet: dict, error_feedback: str | None = None) -> list[dict[str, str]]:
    system = (
        "You are a tafsir methodology classifier. "
        "Reply with a single JSON object only. "
        "Use span ids from the packet; never invent ids; never quote long source text."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": build_user_prompt(packet, error_feedback)},
    ]


def _default_http_post(url: str, headers: dict[str, str], body: bytes) -> bytes:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise ClassifyError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise ClassifyError(f"network error: {e.reason}") from e


def chat_completions_url(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def call_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    http_post: HttpPost | None = None,
) -> str:
    if not api_key:
        raise ClassifyError("LLM_API_KEY is not set")
    if not base_url:
        raise ClassifyError("base_url is empty (set LLM_BASE_URL)")
    url = chat_completions_url(base_url)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    post = http_post or _default_http_post
    raw = post(url, headers, body)
    data = json.loads(raw.decode("utf-8"))
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ClassifyError("unexpected chat completions response shape") from e


def write_moves(out_dir: Path | str, annotator: str, window_id: str, payload: dict) -> Path:
    dest_dir = Path(out_dir) / annotator
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{window_id}.json"
    path.write_bytes(
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    return path


def classify(
    packet_path: Path | str,
    model: str,
    base_url: str,
    out_dir: Path | str,
    *,
    api_key: str | None = None,
    http_post: HttpPost | None = None,
    dry_run: bool = False,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    """Send packet to an OpenAI-compatible endpoint; write moves/<slug>/<window>.json.

    Validates span ids; on failure retries once with the error message, then raises.
    """
    packet = load_packet(packet_path)
    window_id = str(packet.get("window_id") or Path(packet_path).stem)
    if not packet_span_ids(packet):
        rec = make_failure_record(window_id, "RUN_FAILURE", f"packet has no spans: {packet_path}")
        if raise_on_failure:
            raise ClassifyError(
                f"packet has no spans: {packet_path}",
                record=rec,
                reason_code="RUN_FAILURE",
                window_id=window_id,
            )
        return rec

    h = grounding_contract.packet_sha256(packet)
    key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
    messages = build_messages(packet)
    result: dict[str, Any] = {
        "window_id": window_id,
        "model": model,
        "annotator": model_slug(model),
        "dry_run": dry_run,
        "messages": messages,
        "path": None,
        "payload": None,
    }
    if dry_run:
        return result

    # 1st attempt: network call
    try:
        content = call_chat(
            base_url=base_url,
            api_key=key,
            model=model,
            messages=messages,
            http_post=http_post,
        )
    except ClassifyError as e:
        rec = make_failure_record(window_id, "RUN_FAILURE", str(e))
        if raise_on_failure:
            raise ClassifyError(
                str(e), record=rec, reason_code="RUN_FAILURE", window_id=window_id
            ) from e
        return rec
    except Exception as e:
        rec = make_failure_record(window_id, "RUN_FAILURE", str(e))
        if raise_on_failure:
            raise ClassifyError(
                str(e), record=rec, reason_code="RUN_FAILURE", window_id=window_id
            ) from e
        return rec

    # 1st attempt: parse & validate
    first_error: str | None = None
    payload: dict | None = None
    try:
        payload = extract_json_object(content)
        errors = validate_span_ids(packet, payload)
        if errors:
            first_error = "Invalid span ids:\n- " + "\n- ".join(errors)
    except ClassifyError as e:
        first_error = f"Invalid JSON reply: {e}"

    if first_error is not None:
        retry_messages = build_messages(packet, error_feedback=first_error)
        try:
            content = call_chat(
                base_url=base_url,
                api_key=key,
                model=model,
                messages=retry_messages,
                http_post=http_post,
            )
        except ClassifyError as e:
            rec = make_failure_record(window_id, "RUN_FAILURE", str(e))
            if raise_on_failure:
                raise ClassifyError(
                    str(e), record=rec, reason_code="RUN_FAILURE", window_id=window_id
                ) from e
            return rec
        except Exception as e:
            rec = make_failure_record(window_id, "RUN_FAILURE", str(e))
            if raise_on_failure:
                raise ClassifyError(
                    str(e), record=rec, reason_code="RUN_FAILURE", window_id=window_id
                ) from e
            return rec

        try:
            payload = extract_json_object(content)
            errors = validate_span_ids(packet, payload)
            if errors:
                err_msg = "invalid span ids after retry: " + "; ".join(errors[:8])
                rec = make_failure_record(window_id, "MODEL_OUTPUT_INVALID", err_msg)
                if raise_on_failure:
                    raise ClassifyError(
                        err_msg,
                        record=rec,
                        reason_code="MODEL_OUTPUT_INVALID",
                        window_id=window_id,
                    )
                return rec
        except ClassifyError as e:
            err_msg = f"invalid JSON after retry: {e}"
            rec = make_failure_record(window_id, "MODEL_OUTPUT_INVALID", err_msg)
            if raise_on_failure:
                raise ClassifyError(
                    err_msg,
                    record=rec,
                    reason_code="MODEL_OUTPUT_INVALID",
                    window_id=window_id,
                ) from e
            return rec

    assert payload is not None
    cleaned = sanitize_moves_payload(payload, window_id)
    cleaned[grounding_contract.PACKET_SHA_FIELD] = h
    cleaned[grounding_contract.INPUT_ASSURANCE_FIELD] = grounding_contract.INPUT_API_PACKET
    path = write_moves(out_dir, model_slug(model), window_id, cleaned)
    result["path"] = path
    result["payload"] = cleaned
    result["messages"] = messages
    return result


def resolve_env(*, model: str | None = None, base_url: str | None = None) -> tuple[str, str]:
    """Resolve model and base_url from args or LLM_MODEL / LLM_BASE_URL."""
    m = model or os.environ.get("LLM_MODEL") or ""
    b = base_url or os.environ.get("LLM_BASE_URL") or ""
    return m, b
