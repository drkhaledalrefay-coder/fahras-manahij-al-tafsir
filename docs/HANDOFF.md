# Handoff — Tafsir Methodology Index (فهرس مناهج التفسير)

**Written:** 2026-10-03 · **Baseline:** `main@196a6a4` (merge of PR #1) · **For:** the team's programmer and any Claude / Codex session continuing the work.

Read [`AGENTS.md`](../AGENTS.md) first. It is binding. This file says **what to do next**. The audit [`docs/AUDIT_2026-10-02.md`](AUDIT_2026-10-02.md) holds the evidence and the reasons behind each item.

---

## 1. Where things stand

| Item | State | Evidence |
|---|---|---|
| Text integrity (span-ID-only model output, deterministic rebuild) | Works | `python src/v2_selftest.py` → `SELFTEST PASS` |
| Unit tests | 50 run, OK, 2 skipped (need `QURAN_DB`) | `python -m unittest discover -s tests -p "test_*.py"` |
| Browser QA | **Red on purpose**: 16 pass / 10 fail / 2 skip, exit code 1 | `deck/qa/qa_runner.py` (before PR #1 it exited 0 while failing) |
| UI coverage | 3 verses × 4 tafsirs. al-Anfal **not** shown | `src/build_fahras.py` has no `data/anfal` |
| al-Anfal | Text prepared for 4 tafsirs (75 verses each). **No AI run, no verification** | `data/anfal/<tafsir>/` has no `moves/` or `verified/` |
| Specialist approval | **0 units approved** (180 `pending`) | `data/**/verified/` |
| Approval storage | Only in the reviewer's browser (`localStorage`) | `src/fahras_template.html:2536-2545` |
| Repo visibility | **Private** (the challenge requires public) | GitHub API |
| Project score | 65/100, pre-production | Audit §2 |

**Deadline:** submission closes **6 Oct 2026, 23:59 Riyadh time**. Build days are 4–6 Oct (team snapshot in `method/competition_rules_checklist.md`; verify on the live site).

## 2. Blocked on a human decision (do not decide, do not work around)

The owner sent the mentor question on 2026-10-02. The wording is in audit Appendix A-3. **No answer has been received yet.**

1. **Scope:** al-Anfal with al-Tabari only, or all four tafsirs? Is the Ibn Kathir A/B test in scope?
2. **Indexed-text source:** all current text comes from Tafsir Center (`tafsircenter/tafsir-mcp-data`). The owner's direction is Dorar al-Sunniya. The team's own research notes that Dorar's tafsir is rights-reserved and has no API (`method/research_early_sources.md`).
3. **Republication rights** for every text (edition, URL, terms) before the repo or any demo goes public.

**Blocked until answered:** running AI classification on al-Anfal, adding or swapping any source text, making the repo public, and publishing a public demo (see Task 4).

## 3. Tasks you can start now (in this order)

For each task: one branch, one PR. State the files and expected behavior before editing, and report the actual command output.

### Task 1 — Triage QA failures T9–T15 (review screen)

- **Symptom:** in the `light desktop` mode, `T9`–`T15` time out on click. Playwright reports `<aside id="drawer" class="drawer">… intercepts pointer events`.
- **Known facts:**
  - `deck/qa/QA_REPORT.md` (30 Sep) recorded T9 as **PASS**.
  - In isolation, clicking `#start-review-btn` then `#rt-compare-btn` **works** on a fresh page.
  - The review flow now shows an «إضافة إلى التعليق» popover after text selection (screenshot from the 2 Oct run).
- **Question to answer with evidence:** did the UI flow change so the test is stale, or is the drawer wrongly covering controls (a real regression)?
- **Do:** reproduce, find the step where `#drawer` opens, then fix **either** the test (if the flow legitimately changed) **or** the template (if the drawer should not cover those controls).
- **Do not:** raise timeouts, use `force=True` clicks, or skip/delete tests.
- **Done when:** `python deck/qa/qa_runner.py` shows T9–T15 passing for a stated reason. T1 may still fail in a network-blocked environment (Google Fonts plus `favicon.ico` 404). Say so explicitly; don't hide it.
- **Files:** `deck/qa/qa_runner.py` and/or `src/fahras_template.html`, then rebuild with `python src/build_fahras.py`.

### Task 2 — Consolidate duplicated text-integrity helpers into `src/textcore.py`

- **Why:** `_read_exact` exists in 10 files. `_read_json` exists in 9 (two variants). `_sha256_*` exists in 5. `_assert_tiling` exists in 3 files with **3 different bodies**: the `src/multi_layers.py:211` copy (used by the al-Anfal pipeline through `run_surah.py`) skips the last-range-non-empty check that `src/layers.py:116` has. These invariants use `assert`, which `python -O` removes.
- **Do:**
  - Create `src/textcore.py` with `read_exact`, `read_json`, `sha256_bytes`, `sha256_file`, `assert_tiling`.
  - Use the **strictest** `assert_tiling` and raise an explicit `IntegrityError` instead of `assert`.
  - Import it everywhere and delete the copies.
  - Add `tests/test_textcore.py` covering gap, overlap, empty last range, and unsorted input.
- **Done when:**
  - `grep -n "^def _read_exact\|^def _assert_tiling" src/*.py` finds no copies outside `textcore.py`.
  - All unit tests pass.
  - `python src/build_fahras.py` prints the **same** `data_version=4bf26ce1d03a`.
  - `git status -- data` is clean.
- **Do not:** change any output file under `data/`. This is a pure refactor.

### Task 3 — Stop losing specialist decisions (design first, then minimal build)

- **Why:** a reviewer's approve/reject decisions live only in browser `localStorage`. They reach the repo only through a manual export followed by `src/export_approved.py`. Clearing the browser loses them.
- **Do first:** write a one-page proposal (PR description is fine) for a **minimal, file-based** source of truth. For example, export writes `data/<base>/reviews/<reviewer>/<window>.json`, which is committed and validated by `export_approved.py` against `schema/annotation.schema.json`. Include a UI reminder to export before leaving.
- **Needs team approval** before any change to `schema/`. No database or server for this deadline.
- **Done when:** one real decision goes through proposal → `v2_verify` → specialist decision → committed review file → `export_approved.py` → valid record, and survives clearing the browser.
- **Never** create or mark an approval yourself. Only a human specialist approves.

### Task 4 — Stable demo URL (preparation only)

- **Prepare:** a static deploy config for `web/` (Netlify or Cloudflare Pages). Never deploy `src/demo_server.py` publicly; it is local-only by design.
- **Blocker:** a public URL **republishes the tafsir text**, which is the same rights question as §2.3. Deploy only after the owner confirms rights and approves.
- **Known issue:** generated pages have no `<!doctype>` or `<html lang="ar">` (`src/build_fahras.py:451-453` forbids them for claude.ai hosting). On a normal static host this triggers quirks mode. Raise it with the team before changing the builder.

## 4. After the mentor answers

1. Record the decision in `ATTRIBUTION.md`, `AGENTS.md` rule 7, and audit Appendix A.
2. If the current Tafsir Center text is accepted: run al-Anfal for the confirmed tafsir(s), **dry-run first**.
   ```bash
   python src/run_window.py --base data/anfal/al_tabari --window 8_2 --dry-run
   python src/run_window.py --base data/anfal/al_tabari --window 8_2 --api      # needs LLM_* env vars
   python src/v2_verify.py --base data/anfal/al_tabari
   ```
   No API key: use `--manual-out prompt.txt`, then `--manual-in reply.json`.
3. Teach `src/build_fahras.py` to read the confirmed `data/anfal/<tafsir>` base. **Measure** page size before and after (now 1.32 MB raw / 233 KB gzip; load ~0.5 s locally). Split the data into per-surah JSON only if it exceeds about 500 KB gzip or 2 s.
4. If Dorar is required for the indexed text: **stop**. That is a new source, and it needs rights clearance and a new ingestion path decided by the team.

## 5. Gates before every PR

```bash
python src/v2_selftest.py                              # SELFTEST PASS
python -m unittest discover -s tests -p "test_*.py"    # OK (2 skipped without QURAN_DB is expected)
python src/build_fahras.py                             # data_version unchanged unless data changed on purpose
git checkout web/fahras.html                           # unless you are the designated committer
python -m http.server 8791 --directory web &           # then:
python deck/qa/qa_runner.py                            # exit code 0 is the target
git status -- data                                     # nothing under raw/ layers/ spans/ windows/
```

QA browser: Google Chrome if installed, otherwise Playwright Chromium (`python -m playwright install chromium`), or set `QA_CHROMIUM_EXECUTABLE=<path>`.

## 6. Report back in this shape

- Branch and commit.
- Files changed and why.
- Commands run, with their **actual** output (failures included).
- What you could not run and why.
- Anything that needs a human decision.

## 7. Out of scope for this deadline

- A database, an API, or caching (no measurement justifies it yet).
- Rewriting large templates wholesale. Extract shared CSS only when touching that part.
- Merging `ui-mockups` as-is. Use only the ideas marked «adopt now» in audit Appendix B.
- Changing repo visibility (owner only, after §2.3).
