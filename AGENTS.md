# AGENTS.md — rules for AI coding agents (Codex, Claude, Cursor…)

Read this before any change. Human-facing details: [`README.md`](README.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`docs/RUN.md`](docs/RUN.md), [`docs/AI_RUN.md`](docs/AI_RUN.md).

## What this project is

فهرس مناهج التفسير — indexes a commentator's **method** inside classical tafsir text. Code splits the source text into spans; a model proposes span boundaries and method tags **by span ID only**; deterministic code rebuilds and verifies the text letter by letter; a human specialist approves. Status: research pilot, **no unit is specialist-approved yet**.

## Hard rules (never break, never "fix" around)

1. **Never write, edit, normalize, re-type, or paraphrase tafsir text.** Not in `data/`, not in HTML, not in mockups, not in tests. Text only enters through the pinned pipeline (`quran.db` → `src/` scripts, sha256 in `data/raw/manifest.json`).
2. **Never produce an explanation of a verse or a religious answer.** The tool indexes; it does not interpret.
3. **Never change tags, `verified/` outputs, or approval states by hand.** Models write only under `<base>/moves/<annotator>/`; verification output comes from `src/v2_verify.py`. Only a human specialist approves. Do not mark anything `approved`.
4. **Never claim accuracy, approval, or coverage** in docs, UI, or commit messages without evidence in the repo. Do not show sample numbers as results.
5. **No secrets anywhere.** API keys come from `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` env vars only. Never print them, never commit `.env`.
6. **Never commit `quran.db`** (234 MB, gitignored).
7. **Do not decide scope or sources.** Open questions (do not resolve by assumption): al-Anfal with al-Tabari only or four tafsirs; whether the Ibn Kathir A/B test is in scope; whether the indexed text must come from Dorar al-Sunniya (owner's direction) while current data comes from Tafsir Center (`tafsircenter/tafsir-mcp-data`). Do not add, scrape, or swap source text. See `docs/AUDIT_2026-10-02.md` §6.
8. **Do not merge to `main`, push to `main`, or change repo visibility.** Work on your own branch; one branch per person/agent.

## Repo map

| Path | What | Edit? |
|---|---|---|
| `src/*.py` | pipeline, verifier, builders, `demo_server.py` (local only, 127.0.0.1) | yes, with tests |
| `src/*_template.html` | page templates (large; `fahras_template.html` ≈ 6k lines) | yes, small focused edits |
| `web/*.html`, `web/*.json` | **generated** — never hand-edit | rebuild only |
| `data/raw/`, `data/**/raw/`, `layers/`, `spans/`, `windows/` | pinned source text and derived segmentation | **no** |
| `data/**/moves/<annotator>/` | model proposals (span IDs only) | only via `src/run_window.py` |
| `data/**/verified/` | deterministic verifier output | only via `src/v2_verify.py` |
| Data bases | `data/v2` (Ibn Kathir pilot), `data/multi/<tafsir>` (3 verses), `data/anfal/<tafsir>` (al-Anfal, not yet classified) | — |
| `method/` | taxonomy, classifier prompt, research, agent briefs | docs only |
| `schema/` | approved-record JSON schema | no, without team decision |
| `tests/`, `deck/qa/` | unit tests, Playwright QA | yes |

## Commands (run from repo root, Python 3.11+)

```bash
pip install -r requirements.txt
python src/build_fahras.py                      # rebuild web/fahras.html (only build_date changes if data unchanged)
python src/v2_selftest.py                       # must print SELFTEST PASS
python -m unittest discover -s tests -p "test_*.py"   # 2 tests skip without QURAN_DB
python -m http.server 8791 --directory web      # then, in another shell:
python deck/qa/qa_runner.py                     # Playwright QA; exits 1 on any FAIL
```

Classify one window without a key (manual fallback):
`python src/run_window.py --base data/anfal/al_tabari --window 8_2 --dry-run` then `--manual-out prompt.txt` / `--manual-in reply.json`.

## Definition of done for any change

- State the files you will touch and the expected behavior **before** editing.
- Run the tests relevant to your change and report the **actual** output. If a test cannot run, say why; never call it passing.
- `git status -- data` must show nothing under `raw/`, `layers/`, `spans/` or `windows/` unless the team explicitly asked for a source change. Never write to those files, even temporarily to test something.
- `web/fahras.html` is committed only by the designated person; otherwise leave the rebuilt file uncommitted (`git checkout web/fahras.html`).
- Commit only your own paths. No scratch files, screenshots, personal notes, `deck/qa/shots/`, `deck/qa/gallery/`.
- Do not rewrite large files wholesale or add a database/API/cache without measurements that justify it.
