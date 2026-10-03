> **Orchestrator verification (2026-10-03, after this audit):**
> - **P0-1 (CI pathspec) — NOT REPRODUCED.** `main@c91ebf7` `ci.yml` already lists four separate pathspecs (`data/**/raw/**`, `layers`, `spans`, `windows`), which match 2,341 tracked files; a controlled edit to `data/anfal/al_baghawi/raw/8_1.txt` was reported by the guard's exact `git diff` command. The brace form quoted below does not exist in `main`.
> - **P0-2 (republication rights)** — owner decision recorded: publish code and full texts with source attribution (see `ATTRIBUTION.md`).
> - **P1-1 (unescaped fields in `methods.html`)** — confirmed; fixed in a separate PR (`fix/methods-escape`).

# Read-only audit — فهرس مناهج التفسير

**Baseline:** `main@c91ebf7`, clean working tree. This is a static site built from an offline Python pipeline, with a separate localhost-only demo server. No files were changed.

## Executive Verdict

**Needs Major Refactoring under the requested scoring rubric.** The static architecture fits the pilot, and the text-integrity design has meaningful safeguards. Public release is blocked by an ineffective CI guard for pinned source paths and unresolved republication rights. A model-supplied field also reaches an unescaped HTML sink in the older `methods.html` view; exploitability was established by code tracing, not a browser test.

The score measures engineering and release risk. It does **not** measure classification accuracy or specialist approval. The repo states that no unit is specialist-approved.

## Composite Score

**6.0 / 10** — arithmetic mean of the seven scores.

| Dimension | Score | Label | Main finding |
|---|---:|---|---|
| Infrastructure & Edge Resilience | 6 | Acceptable (minor gaps) | Loopback binding and static-host headers exist; the demo API has no rate limit, appropriate only while kept local. |
| API Design & Network Optimization | 8 | Solid | No public API or N+1 database path; the main page is a 1.32 MB static payload. |
| Caching Strategy | 7 | Acceptable (minor gaps) | Static-host TTLs are configured; specialist decisions depend on browser storage and manual export. |
| Concurrency, Database & Data Integrity | 4 | At Risk (notable gaps) | Strict tiling checks exist, but the CI frozen-path guard matches zero files. |
| Authentication & Session Lifecycle | 5 | Acceptable (minor gaps) | Auth and sessions are unnecessary for the static site; review decisions have no durable, authenticated source of truth. |
| Architecture & Code Maintainability | 5 | Acceptable (minor gaps) | Shared text helpers were consolidated; large, overlapping page templates and an unsafe legacy rendering path remain. |
| Tech Stack Suitability | 7 | Acceptable (minor gaps) | Static hosting plus offline Python suits this pilot; browser QA is absent from CI. |

## Critical Vulnerabilities & Blockers

1. **P0 — CI does not protect pinned source paths.** [`.github/workflows/ci.yml:47`](../../.github/workflows/ci.yml:47) uses `:(glob)data/**/{raw,layers,spans,windows}/**`. `git ls-files` matched **0** tracked files with that expression; the four separate pathspecs matched **2,341**. The base-diff gate can therefore pass after a modification to a pinned file. Its post-build check uses separate paths and does match them.

2. **P0 before public release — text republication rights and source direction remain unresolved.** [`ATTRIBUTION.md:5`](../../ATTRIBUTION.md:5) describes a CC BY 4.0 dataset alongside a stated restriction on commercial redistribution; [`docs/AUDIT_2026-10-02.md:237`](../../docs/AUDIT_2026-10-02.md:237) records unresolved edition and rights questions. The owner’s Dorar al-Sunniya direction and the current Tafsir Center source also remain an open decision. **[UNVERIFIED]** Legal permission for publishing every included text was not established by this code audit.

3. **P1 before publishing `methods.html` — stored XSS path.** [`src/classify_api.py:120`](../../src/classify_api.py:120) retains model-supplied `alternatives`; [`src/v2_verify.py:507`](../../src/v2_verify.py:507) carries them into verified output; [`src/methods_template.html:2105`](../../src/methods_template.html:2105) joins them into a string assigned to `innerHTML` at line 2111 without escaping. The configured CSP permits inline scripts. **[UNVERIFIED]** No live exploit or malicious value in committed data was tested.

## Detailed Findings

- **Infrastructure and secrets:** [`src/demo_server.py:556`](../../src/demo_server.py:556) refuses nonlocal bind addresses. API calls check Host and Origin, cap request bodies at 4,096 bytes, and allow one run at a time. [`netlify.toml:1`](../../netlify.toml:1) publishes only `web/` and sets security headers. No tracked `.env` file or `.env` history entry was found; no environment template exists. A comprehensive secret scan is **[UNVERIFIED]**.

- **Payload and caching:** No database-backed list or reference-data API exists, so N+1 queries, pagination, migration indexes, transactions, and cache invalidation for server mutations do not apply. The checked-in [`web/fahras.html`](../../web/fahras.html) is **1,324,101 bytes** in this checkout. Netlify config gives HTML and JSON a 300-second TTL. Current compressed size and live load time are **[UNVERIFIED]** here; the figures in [`docs/AUDIT_FIXES.md`](../../docs/AUDIT_FIXES.md) describe an earlier build.

- **Review persistence:** [`src/fahras_template.html:2537`](../../src/fahras_template.html:2537) loads decisions from `localStorage`, and `saveLog` silently ignores storage failure. The export envelope and [`src/import_reviews.py:154`](../../src/import_reviews.py:154) provide a validated manual import path, but a decision can still be lost before export or made on a different browser without a shared record. Schema and text-fidelity checks do not establish reviewer identity.

- **Integrity and maintainability:** [`src/textcore.py:39`](../../src/textcore.py:39) has explicit gap, overlap, empty-range, and coverage checks. Search found one `read_exact` and one `assert_tiling` definition, supporting the claimed consolidation. The main and reader templates remain large parallel implementations. Search found no `TODO`, `FIXME`, `HACK`, or `workaround` comments in the scanned code; that is not evidence of no technical debt.

- **Build and QA:** [`src/build_fahras.py:127`](../../src/build_fahras.py:127) escapes `<` in embedded JSON and sorts keys. CI runs unit tests, selftest, and a twice-built byte comparison, but [`ci.yml:31`](../../.github/workflows/ci.yml:31) does not check that the rebuilt output equals the committed `web/` output or run browser QA. The generated page lacks a doctype and `html lang`, as documented in [`docs/DEPLOY.md:18`](../../docs/DEPLOY.md:18).

- **Dependencies and verification limits:** [`requirements.txt`](../../requirements.txt) pins `jsonschema==4.26.0` and `playwright==1.63.0`; Playwright is for QA. A complete transitive-dependency vulnerability check is **[UNVERIFIED]**. `python`, `py`, and `pytest` were unavailable in this shell, so selftest, unit tests, build, and Playwright QA were **not run**. The working tree and `git status -- data` remained clean.

## Remediation Action Plan

**P0 — Before making the repo public**

1. Replace the brace pathspec in the CI base-diff guard with four separate pathspecs. Prove the gate fails on a controlled change to an existing pinned file.
2. Obtain and record the owner’s decisions on indexed-text source, scope, and republication rights for each included edition. Keep the repo private and the static site unpublished until those decisions permit publication.

**P1 — Before a public demo**

1. Render `alternatives` and other variable fields in `methods.html` with text nodes or context-appropriate escaping; test the model-output-to-browser path with hostile strings. Review the other `innerHTML` sinks by the same standard.
2. Add a CI check that generated `web/` artifacts match the committed build, and run the existing browser QA gate in CI.
3. Make review export and validated import a required specialist workflow, with an explicit warning when browser storage fails.

**P2 — After release blockers**

1. Measure compressed payload and load time for the current build and again if al-Anfal is added; split assets only if measurements warrant it.
2. Resolve the doctype and Arabic language metadata for the chosen hosting channel.
3. Run a dependency audit and the full Python and browser test suite in an environment with Python and Playwright installed.