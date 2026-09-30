"""Normalization levels for tafsir text comparison.

Each rule is a separate function. L0 is identity. L1 applies documented
mechanical transforms only — it does not paraphrase or "clean" meaning.

IMPORTANT: Do NOT fold taa marbuta (ة→ه), alif maqsura (ى→ي), or hamza forms.
Those orthographic differences must remain visible for integrity review.
"""

from __future__ import annotations

import re
import unicodedata

# Salawat symbol → expanded form (task-specified unification).
# The expansion string is a fixed normalization target required by the L1 spec,
# not a tafsir source quotation.
_SALAWAT_SYMBOL = "\ufdfa"  # ﷺ
_SALAWAT_EXPANDED = "\u0635\u0644\u0649 \u0627\u0644\u0644\u0647 \u0639\u0644\u064a\u0647 \u0648\u0633\u0644\u0645"

# Tashkeel / combining marks to strip (U+064B–U+065F, U+0670).
_TASHKEEL_RE = re.compile("[\u064b-\u065f\u0670]")

# Tatweel / kashida.
_TATWEEL = "\u0640"

# Quranic / ornamental brackets and quote marks to strip.
_ORNAMENTAL = {
    "\ufd3f",  # ﴿
    "\ufd3e",  # ﴾
    "\u00ab",  # «
    "\u00bb",  # »
    "\u201c",  # "
    "\u201d",  # "
    "\u2018",  # '
    "\u2019",  # '
    '"',
    "'",
}

# Footnote markers: (١) / (1) / [1] / [١٢] etc.
_FOOTNOTE_RE = re.compile(
    r"[\(\[][0-9\u0660-\u0669\u06f0-\u06f9]+[\)\]]"
)

# Whitespace collapse.
_WS_RE = re.compile(r"\s+")


def l0_raw(text: str) -> str:
    """L0: raw text with no change."""
    return text


def remove_tashkeel(text: str) -> str:
    """L1 rule: remove Arabic tashkeel (U+064B–U+065F) and dagger alif (U+0670)."""
    return _TASHKEEL_RE.sub("", text)


def remove_tatweel(text: str) -> str:
    """L1 rule: remove tatweel / kashida (U+0640)."""
    return text.replace(_TATWEEL, "")


def collapse_whitespace(text: str) -> str:
    """L1 rule: collapse all whitespace runs to a single space and strip ends."""
    return _WS_RE.sub(" ", text).strip()


def strip_ornamental_brackets(text: str) -> str:
    """L1 rule: strip Quranic/ornamental brackets ﴿﴾ «» and curly/straight quotes."""
    return "".join(ch for ch in text if ch not in _ORNAMENTAL)


def strip_punctuation(text: str) -> str:
    """L1 rule: remove Unicode punctuation (category P*) after ornamental strip.

    Leaves letters, marks (except those already removed), numbers, and symbols
    that are not punctuation. Does not fold letter forms.
    """
    return "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))


def remove_footnote_markers(text: str) -> str:
    """L1 rule: remove footnote markers like (١), (1), [1], [١٢]."""
    return _FOOTNOTE_RE.sub("", text)


def unify_salawat(text: str) -> str:
    """L1 rule: unify ﷺ with the expanded form صلى الله عليه وسلم."""
    return text.replace(_SALAWAT_SYMBOL, _SALAWAT_EXPANDED)


def l1_normalize(text: str) -> str:
    """Apply L1 rules in a fixed order.

    Order:
      1. unify_salawat
      2. remove_footnote_markers
      3. remove_tashkeel
      4. remove_tatweel
      5. strip_ornamental_brackets
      6. strip_punctuation
      7. collapse_whitespace
    """
    text = unify_salawat(text)
    text = remove_footnote_markers(text)
    text = remove_tashkeel(text)
    text = remove_tatweel(text)
    text = strip_ornamental_brackets(text)
    text = strip_punctuation(text)
    text = collapse_whitespace(text)
    return text


def normalize(text: str, level: str = "L1") -> str:
    """Normalize text to the requested level ('L0' or 'L1')."""
    level = level.upper()
    if level == "L0":
        return l0_raw(text)
    if level == "L1":
        return l1_normalize(text)
    raise ValueError(f"Unknown normalization level: {level}")
