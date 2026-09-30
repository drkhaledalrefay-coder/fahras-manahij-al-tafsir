# QA Report — web/fahras.html

Driven with Python Playwright (Chrome channel, headless) against `python -m http.server 8791 --directory web`.

| Test | Light desktop | Dark desktop | Light phone |
|---|---|---|---|
| T1 Load | PASS | PASS | PASS |
| T2 Tafsir dropdown | PASS | PASS | PASS |
| T3 Verse × tafsir (12) | PASS | — | — |
| T4 Model dropdown | PASS | — | — |
| T5 Methods panel | PASS | — | — |
| T6 Drawer open/close | **FAIL** | not retested | not retested |
| T7 Side-by-side (12) | PASS 12/12 | — | — |
| T8 Fidelity self-test | PASS (n=12) | — | — |
| T9 Review/highlight/approve | PASS | — | — |
| T10 Boundary tools | PASS | — | — |
| T11 Export + schema | **FAIL** | — | — |
| T12 Help panel | PASS | — | — |
| T13 Text size persistence | PASS | — | — |
| T14 Theme + contrast | PASS | PASS | PASS |
| T15 Collapsible sections | PASS | — | — |
| T16 Keyboard focus | PASS | — | — |
| T17 Visual sanity | PASS | PASS | PASS |
| T18 White-box-in-dark bug | PASS (none found) | PASS (none found) | PASS (none found) |

T1, T2, T7, T14, T17, T18 ran in dark/phone per scope and passed there. T3–T13/T15/T16 ran full-depth only in light desktop, passing except T6/T11.

## FAILs

**T6 — drawer Esc does not close** (light desktop). Steps: click a highlight to open «لماذا هذا التمييز؟» → press `Esc`. Expected: closes (spec requires button + Esc). Actual: stays open; only the close button works. Cause: the global `keydown` handler (~line 5133) checks help panel/export menu/delete-confirm for Escape but has no `#drawer` branch. Screenshot: `gallery/03_why_drawer.png`.

**T11 — exported JSON fails schema validation** (light desktop). Steps: «ابدأ المراجعة» → select text → add highlight → «قارن بالمصدر» → «اعتماد» → «تصدير ▾» → «تصدير هذا الموضع». `review.changes[]` entries carry `window`/`tafsir`/`annotator`; `tafsir` and `annotator` aren't allowed by `schema/annotation.schema.json`'s `$defs/change` (`additionalProperties:false`), so `jsonschema.validate` fails: "Additional properties are not allowed ('annotator', 'tafsir' were unexpected)". The record itself is otherwise correct (`text` matches source slice, `strict_match: true`). Screenshot: `gallery/06_export.png`.

## Console errors
Only `Failed to load resource: 404 (favicon.ico)` in all three modes — benign, not a functional error; no JS `pageerror`/exceptions observed.

## Verdict: **غير جاهز**
Two real defects found (T6 Esc-close, T11 export/schema mismatch); everything else — load, dropdowns, fidelity self-test (12/12), side-by-side (12/12), review→approve flow, boundaries, contrast, and the reported dark white-box bug (not reproduced, looks fixed) — passes cleanly.

---

## Fix pass 2026-09-29 PM

Rebuilt `web/fahras.html` via `python src/build_fahras.py`. Gates: `deck/qa/qa_fixpass_pm.py`, `deck/qa/qa_followup2.py`, `deck/qa/qa_schema_check.py`.

| Gate | Result | Notes |
|---|---|---|
| Build + fidelity self-test | **PASS** | `data-fidelity-selftest=PASS` n=12 |
| Side-by-side (T7) | **PASS** | 12/12 |
| **T6** Esc closes drawer + focus restore | **PASS** | Esc hides `#drawer`; focus returns to `[data-hid]` that opened it |
| **T9** Review → compare → approve | **PASS** | Pen toolbar visible; compare/approve works |
| **T11** Export + jsonschema | **PASS** | `review.changes[]` stripped of `tafsir`/`annotator`; validates against `schema/annotation.schema.json` |
| Methods one-line (desktop) | **PASS** | `white-space:nowrap` + `title`; shot `gallery/20_methods_oneline_desktop.png` |
| Methods one-line (375px) | **PASS** | shot `gallery/21_methods_oneline_375.png` |
| Verse collapsible | **PASS** | «إخفاء الآية / إظهار الآية», ~22px, localStorage; shot `gallery/22_verse_collapsed.png` |
| Review toolbar light | **PASS** | «🖊 قلم التمييز» + method + tools; contrast ≈17:1; shot `gallery/23_review_toolbar_light.png` |
| Review toolbar dark | **PASS** | contrast ≈14:1; shot `gallery/24_review_toolbar_dark.png` |
| Review toolbar 375 no-cover | **PASS** | compact bar (~51px); does not cover tafsir |
| Drawer markers via textContent | **PASS** | already used `textContent` / DOM APIs (no unescaped innerHTML for marker phrases) |

**Verdict: جاهز** for the listed fix set.
