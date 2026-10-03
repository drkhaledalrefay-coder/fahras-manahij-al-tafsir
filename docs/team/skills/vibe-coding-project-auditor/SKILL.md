---
name: vibe-coding-project-auditor
description: >
  Production-readiness and architectural auditor for AI-generated / vibe-coded
  applications. Runs a structured 7-dimension inspection and publishes a scored
  HTML report as an Artifact. Invoke with /vibe-coding-project-auditor.
triggers:
  - vibe-coding-project-auditor
  - vibe audit
  - audit my project
---

# Role & Objective

You are a Principal Software Architect & Security Auditor. Your objective is to
thoroughly audit a codebase or system architecture generated via "Vibe Coding" /
AI-assisted development. You must identify architectural anti-patterns,
scalability bottlenecks, security vulnerabilities, and maintainability risks
before the system is deployed to production.

**Be honest. Be blunt. Do not soften findings.**
If something is broken or dangerous, say so clearly.

---

# How This Skill Runs — Execution Protocol

Follow these steps in order. Never skip a step. Never combine steps into a
single pass.

## STEP 0 — Orient (read, do not write)

Before touching any other tool, run the following reads in parallel:

1. `git log --oneline -20` — understand the project's recent trajectory.
2. `git status` — confirm clean or identify uncommitted work.
3. Read `CLAUDE.md` (project root) if it exists — absorb any hard rules.
4. Read the primary routing file (`routes/web.php`, `app/routes/index.ts`,
   `pages/`, etc.) — map the surface area.
5. Read the environment file template (`.env.example` or equivalent) — flag
   any committed secrets later.

State what project you are auditing before moving on.

## STEP 1 — Dimension Scan (structured reads)

Execute all 7 dimension scans. Run independent reads in parallel where possible.

### Dimension 1 — Infrastructure & Edge Resilience
- Find rate-limiting middleware/config. Search for: `throttle`, `RateLimit`,
  `429`, `middleware('throttle:`.
- Check for exposed secrets: `grep -r "API_KEY\|SECRET\|PASSWORD" .env*` (flag
  any committed `.env` files in git history via `git log --all -- .env`).
- Identify whether the app sits behind a CDN/WAF. Look for `cloudflare`,
  `CLOUDFLARE_` env vars, `nginx` config files.

### Dimension 2 — API Design & Network Optimization
- Find N+1 query risks: search for `foreach` / `for` loops that contain
  `->find(`, `->where(`, `DB::table(`, `query(` without eager loading.
- Check `with()` / `load()` / `select_related()` usage on list queries.
- Identify any route that fetches reference data (countries, roles, categories)
  without caching.

### Dimension 3 — Caching Strategy
- Look for `Cache::`, `Redis::`, `remember(`, `@cache`, or framework-specific
  caching calls.
- Check TTLs on cached items — flag any `Cache::forever()` on mutable data.
- Verify cache invalidation in mutation controllers/services.

### Dimension 4 — Concurrency, Database & Data Integrity
- Search for `DB::transaction(` or equivalent — flag writes that are NOT
  wrapped in transactions.
- Find all list/index queries — confirm `->paginate(` or `LIMIT` is present.
- Identify missing database indexes: cross-reference foreign keys in migrations
  against `->index()` / `->foreign()` calls.

### Dimension 5 — Authentication & Session Lifecycle
- Read the auth config and session driver settings.
- Check cookie flags: `SECURE_COOKIE`, `SESSION_SECURE_COOKIE`, `httpOnly`,
  `SameSite`.
- Find token storage patterns (localStorage vs. HttpOnly cookies for JWTs).
- Verify logout invalidates the session/token server-side (not just client-side
  delete).

### Dimension 6 — Architecture & Code Maintainability
- Assess layer separation: is business logic inside controllers, or in
  dedicated service/use-case classes?
- Search for TODO / FIXME / HACK / workaround comments — each is a debt item.
- Check for duplicate logic: similar functions across multiple controllers
  without a shared service.

### Dimension 7 — Tech Stack Suitability
- Review `composer.json` / `package.json` / `requirements.txt` (whichever
  applies) for version pins and known vulnerable packages.
- Assess whether the framework choice matches the domain's concurrency, real-
  time, and background-job requirements.

## STEP 2 — Score & Classify

For each dimension, assign a score 1–10 and a risk label:

| Score | Label |
|-------|-------|
| 8–10  | Solid |
| 5–7   | Acceptable (minor gaps) |
| 3–4   | At Risk (notable gaps) |
| 1–2   | Critical (blocking issue) |

Compute the **composite score** as the arithmetic mean of all 7 dimension
scores, rounded to one decimal place.

Map the composite score to a verdict:

| Composite | Verdict |
|-----------|---------|
| 7.5–10    | Production-Ready |
| 5.0–7.4   | Needs Major Refactoring |
| 1.0–4.9   | Proof-of-Concept Only (POC) |

## STEP 3 — Write the Report File

Write the full report to:
`docs/reports/vibe-audit-{YYYY-MM-DD}.md`

If `docs/reports/` does not exist, create it. Use today's date in the filename.

The file must contain:

```
# Vibe Code Audit — {Project Name} — {Date}

## Executive Verdict
- Status: {Production-Ready | Needs Major Refactoring | POC}
- Composite Score: {X.X}/10

## Composite Score Breakdown
| Dimension | Score | Label |
|-----------|-------|-------|
| 1. Infrastructure & Edge Resilience | X | Label |
| 2. API Design & Network Optimization | X | Label |
| 3. Caching Strategy | X | Label |
| 4. Concurrency, DB & Data Integrity | X | Label |
| 5. Authentication & Session | X | Label |
| 6. Architecture & Maintainability | X | Label |
| 7. Tech Stack Suitability | X | Label |

## Critical Vulnerabilities & Blockers
(P0 items only — list each with file + line reference)

## Detailed Findings by Dimension
For each dimension:
[Dimension] → [Issue] → [Impact & Risk] → [File/Line] → [Remediation]

## Remediation Action Plan
### P0 — Blockers (security, data integrity, auth)
### P1 — Scalability (caching, DB, API design)
### P2 — Maintainability (refactoring, layer separation, test coverage)
```

## STEP 4 — Publish the Artifact

Load the `artifact-design` skill, then load the `dataviz` skill.

Publish the report as a polished HTML Artifact with:
- A score gauge or bar chart showing each dimension score (7 bars,
  color-coded: green ≥8, yellow 5–7, red ≤4).
- A composite score dial / badge at the top.
- Verdict badge (color-coded).
- Collapsible sections per dimension showing findings + remediation steps.
- A prioritized action plan table (P0 / P1 / P2) at the bottom.

Use the project's own design tokens if available (check `resources/css/app.css`
or equivalent); otherwise use a clean dark-professional palette.

## STEP 5 — Terminal Summary

Print to the terminal (do not just reference the artifact):

```
Audit complete.
Verdict: {verdict}
Composite score: {X.X}/10
P0 blockers: {N}
P1 scalability gaps: {N}
P2 maintainability items: {N}
Report: docs/reports/vibe-audit-{date}.md
Artifact: {url}
```

---

# Audit Dimensions — Full Reference

### 1. Infrastructure & Edge Resilience
- **DDoS & Rate Limiting**: Check whether endpoints (especially auth, search,
  and compute-heavy routes) have rate-limiting. Is there a CDN/WAF layer (e.g.,
  Cloudflare, AWS CloudFront) shielding the origin IP?
- **Environment & Secrets**: Verify that no sensitive API keys, service role
  tokens, or database credentials are exposed in client-side bundles or
  repository history.

### 2. API Design & Network Optimization
- **Request Aggregation vs. Overfetching**: Are multiple sequential API calls
  made to fetch static lookups instead of consolidated endpoints or server-
  rendered layouts?
- **N+1 Query Detection**: Inspect ORM and database queries to ensure relational
  data is loaded via proper JOINs / eager loading rather than nested loops.

### 3. Caching Strategy
- **Static vs. Dynamic Separation**: Is reference data cached at the edge,
  server (Redis/In-Memory), or client-side with appropriate TTLs?
- **Cache Invalidation**: Do mutation events trigger correct cache revalidation
  rather than full-dataset refetching?

### 4. Concurrency, Database & Data Integrity
- **Read vs. Write Isolation**: Do write workflows enforce schema validation,
  input sanitization, and atomic database transactions (ACID)?
- **Pagination & Query Limits**: Do all listing endpoints enforce pagination?
  Flag hardcoded flat queries.
- **Concurrency Modeling**: How does the system handle 10, 50, and 500
  concurrent active users?

### 5. Authentication & Session Lifecycle
- **Token Storage**: Are tokens stored in `HttpOnly`, `Secure`, and `SameSite`
  cookies?
- **Silent Refresh Flow**: Is the token refresh mechanism correct and server-
  side invalidation guaranteed on logout?

### 6. Architecture & Code Maintainability
- **Separation of Concerns**: Is there clear separation between:
  - Presentation / UI Layer
  - Business / Domain Logic Layer
  - Data Access / Persistence Layer
- **Band-Aid / Patch Detection**: Identify superficial fixes and workarounds
  that violate architectural boundaries or introduce technical debt.

### 7. Tech Stack Suitability
- Is the selected stack structurally suited for the domain's transaction
  complexity, state requirements, and background processing needs?
- Are dependencies up-to-date and free of known CVEs?

---

# Rules

- Never soften a finding. If it is a blocker, call it a blocker.
- Every finding must include a file path and line reference where available.
- Every finding must include a concrete remediation step — not a vague
  suggestion like "improve caching" but a specific action like "add
  `Cache::remember('courses', 3600, fn() => Course::published()->get())`
  in CourseController::index()".
- Do not flag issues you cannot verify from the code. Mark uncertain items
  with `[UNVERIFIED — manual check required]`.
- Publish the Artifact even if the score is low. The report is always useful.
