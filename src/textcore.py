"""Shared text/path helpers for the pinned pipeline.

One authoritative copy of the helpers that were previously duplicated across
src/*.py (see docs/AUDIT_2026-10-02.md §3 / phase 2.1). Callers import from here;
do not re-define these functions elsewhere.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IntegrityError(ValueError):
    """Raised when text/span integrity checks fail (tiling, coverage, …)."""


def read_exact(path: Path) -> str:
    """Read a pinned text file as UTF-8 without newline translation."""
    return path.read_bytes().decode("utf-8")


def read_json(path: Path) -> dict:
    """Load a UTF-8 JSON object from disk (bytes → decode → json.loads)."""
    return json.loads(path.read_bytes().decode("utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def assert_tiling(ranges: list[dict], n: int) -> None:
    """Strict tiling check: sorted, abutting, non-empty, covering [0, n).

    Combines the strongest checks from the former copies in layers.py,
    multi_layers.py, and check_phase1b.py. Uses explicit exceptions so
    ``python -O`` cannot strip the guard.
    """
    if ranges != sorted(ranges, key=lambda r: r["start"]):
        raise IntegrityError("ranges not sorted by start")
    if n == 0:
        if ranges:
            raise IntegrityError("expected no ranges for empty text")
        return
    if not ranges:
        raise IntegrityError("ranges empty but text length > 0")
    if ranges[0]["start"] != 0:
        raise IntegrityError("ranges do not start at 0")
    if ranges[-1]["end"] != n:
        raise IntegrityError("ranges do not end at len(text)")
    prev_end = 0
    for r in ranges:
        start = r["start"]
        end = r["end"]
        if start != prev_end:
            raise IntegrityError(f"gap/overlap at {prev_end} vs {start}")
        if end <= start:
            raise IntegrityError(f"empty range at {start}")
        prev_end = end
    if prev_end != n:
        raise IntegrityError(f"ranges end at {prev_end}, expected {n}")


def resolve_base(base: str | Path, root: Path | None = None) -> Path:
    """Resolve a ``--base`` path relative to the repo root (or ``root``)."""
    p = Path(base)
    if not p.is_absolute():
        p = (root or ROOT) / p
    return p.resolve()
