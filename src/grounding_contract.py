"""Grounding contract shared by classifier, runner and verifier (Phase 0).

Closed list of abstention / referral reason codes, plus the field names that
bind a model reply to the exact packet it was produced from. Every move routed
to ``specialist`` carries exactly one ``reason_code`` from REASON_CODES; when
several apply, the first in REASON_CODES order wins (most fundamental first).
"""

from __future__ import annotations

import hashlib
import json

# Ordered by priority: earlier = more fundamental failure.
REASON_CODES: dict[str, str] = {
    "RUN_FAILURE": "تعذّر التشغيل (شبكة/مهلة/خطأ نموذج) — لا اقتراح",
    "MODEL_OUTPUT_INVALID": "رد النموذج غير صالح (JSON أو مخطط أو معرّفات) بعد إعادة المحاولة",
    "PACKET_HASH_MISSING": "الرد غير مربوط ببصمة الحزمة",
    "PACKET_HASH_MISMATCH": "بصمة الحزمة في الرد لا تطابق الحزمة الحالية",
    "MANUAL_INPUT_UNVERIFIED": "رد يدوي من محادثة خارجية — المدخل غير مضمون",
    "BOUNDARY_INVALID": "حدود الحركة غير سليمة (معرّف مجهول أو أجزاء غير متصلة)",
    "EVIDENCE_EMPTY": "لا شاهد صريح — لا يولّد الفاحص شاهداً بديلاً",
    "EVIDENCE_OUTSIDE_MOVE": "الشاهد خارج نطاق الحركة المسموح",
    "VERDICT_FAR_FROM_MOVE": "شاهد حكم المؤلف بعيد عن الحركة",
    "EDITOR_ONLY_EVIDENCE": "الشاهد الوحيد حاشية محقق لا نص المؤلف",
    "CONFLICTING_EVIDENCE": "علامات الشاهد تدل على منهج مختلف عن المدّعى",
    "UNGROUNDED_CLAIM": "مرجع أو ادعاء معروض بلا شاهد يسنده",
    "INSUFFICIENT_EVIDENCE": "بوابة كفاية الدليل لم تُجتز",
    "FORCED_SPECIALIST_METHOD": "منهج يُحال دائماً للمتخصص (رأي/إسرائيليات/نزول/قراءات)",
    "MIXED_SPAN": "تداخل أو اشتراك أجزاء مع حركة أخرى",
    "RULE_FLAG": "قاعدة فحص أخرى لم تُجتز",
    "LOW_CERTAINTY": "يقين ضعيف أو غير كافٍ",
    "LOW_SCORE": "الدرجة دون العتبة",
}

ROUTE_AUTO = "auto_candidate"
ROUTE_SPECIALIST = "specialist"

# Fields a moves payload carries (written by classify_api / run_window,
# checked by v2_verify).
PACKET_SHA_FIELD = "packet_sha256"
INPUT_ASSURANCE_FIELD = "input_assurance"
INPUT_API_PACKET = "api_packet"  # built by code from the registered packet only
INPUT_MANUAL_UNVERIFIED = "manual_unverified"  # pasted from any chat: never nominated


def pick_reason(codes: list[str]) -> str:
    """Return the single highest-priority code; raise on unknown codes."""
    unknown = [c for c in codes if c not in REASON_CODES]
    if unknown:
        raise ValueError(f"unknown reason codes: {unknown}")
    if not codes:
        raise ValueError("pick_reason needs at least one code")
    order = list(REASON_CODES)
    return min(codes, key=order.index)


def packet_sha256(packet: dict) -> str:
    """Canonical hash of a packet (key-sorted, UTF-8, no whitespace)."""
    canonical = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
