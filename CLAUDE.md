# CLAUDE.md

Project notes for AI coding sessions. Keep this file current: update Current State and Next Steps when work lands.

## Project
Sell-side research engine: a Python pipeline that fetches market, SEC and macro data, screens stocks, runs DCF / reverse DCF / risk analytics, and writes research notes. A static dashboard (`index.html`) is deployed on Vercel at https://sellside-research-engine.vercel.app and reads `dashboard_data.json`.

Stack: Python 3.12 (pandas, yfinance, scipy, plotly, matplotlib, weasyprint), vanilla JS with Chart.js and Plotly from cdnjs, Vercel static hosting, GitHub Actions.

## Architecture
```
python main_v2.py fetch-all --as-of D     -> data/normalized/*_D.csv   (gitignored)
python export_dashboard_data.py --as-of D --skip-fetch -> dashboard_data.json (committed)
index.html fetch('dashboard_data.json')   -> renders the dashboard
python main_v2.py build-report --as-of D  -> outputs/research_note_D.html (gitignored)
```
- One valuation path: `trg_workbench/pipeline_v2.py::value_ticker()` is used by both the report and the dashboard export. Do not reimplement DCF logic elsewhere.
- Deploys: the Vercel Git integration deploys every push to `main` and a preview for every PR. There is no deploy workflow (the old token-based one was removed).
- Data refresh: `.github/workflows/refresh-data.yml` runs weekdays at 22:00 UTC (plus manual dispatch). It fetches, exports, validates the JSON strictly, and commits `dashboard_data.json` as github-actions[bot] only if it changed. That push triggers the deploy.

## File Map
| Path | Role |
|---|---|
| `main_v2.py` | CLI: `fetch-all`, `build-report`, `build-all`, `--dry-run` checks |
| `trg_workbench/pipeline_v2.py` | Orchestration: `fetch_data_v2`, `value_ticker`, `build_research_report_v2`, `_load_*` helpers |
| `trg_workbench/pipeline.py` | v1 fetch (market, SEC, ECB), called by v2 |
| `trg_workbench/analytics/screening.py` | `build_research_dataset` (factor scores 0..1, analyst targets, earnings dates), `top_screen_candidates` |
| `trg_workbench/analytics/valuation.py` | `derive_dcf_inputs`, `scenario_analysis`, `dcf_sensitivity`, `reverse_dcf`, `football_field` |
| `trg_workbench/analytics/risk.py` | `build_risk_table` (vol, beta, Sharpe, Sortino, drawdown, VaR/CVaR 1d) |
| `trg_workbench/analytics/summaries.py` | `build_catalyst_calendar` and report summaries |
| `trg_workbench/llm/` | Transcript fetch + heuristic commentary (`build_management_commentary`) |
| `trg_workbench/reporting/` | Charts, HTML/PDF/Markdown renderers, Jinja templates |
| `trg_workbench/sources/` | Market (yfinance), SEC, ECB, US macro clients |
| `export_dashboard_data.py` | Builds `dashboard_data.json` from normalized data |
| `index.html` | Dashboard (single file, JSON loaded at runtime) |
| `vercel.json` | Static build of `index.html` + `dashboard_data.json`, filesystem first, then SPA fallback |
| `tests/` | pytest suite (`pytest -q`), incl. `test_export_dashboard.py` |

## Current State (2026-09-23)
- Prod is live on real data, refreshed by the bot on weekdays.
- 2026-09-21: an AI agent (qwen.ai[bot]) merged PRs #47/#48 that broke prod (JSON routed to HTML, `NaN` in JSON, export script with wrong keys and swapped args, committed cache junk). Reverted in #49, rebuilt properly in #50.
- Open PRs: #51 (dates parse as local noon, fixes off-by-one for US viewers), #52 (`derive_dcf_inputs` reads snake_case security-master columns, so net_debt and market_cap are no longer 0 in the DCF).

## Next Steps
1. Review and merge #51 and #52; check the Vercel preview first.
2. Optional: add a `SEC_USER_AGENT` repo secret with a contact address for SEC requests.
3. Beta shows n/a: SPY is not in the price universe (`trg_workbench/config.py`).
4. Management commentary shows n/a: no cached earnings transcripts (`TRG_FETCH_TRANSCRIPTS=1` fetches live).
5. Plotly interactive charts (issue #10) were never wired end to end; build-report forces `static=True` as a stopgap.

## Gotchas
- Keep the legacy `builds` in `vercel.json`. Without it Vercel may auto-detect `requirements.txt` / `main.py` as a Python app. Any new static file the page fetches must be added to `builds`.
- Export writes JSON with `allow_nan=False`. Missing values become `null` and render as `n/a`. Never fill gaps with invented numbers or placeholder text.
- `data/`, `outputs/`, `.venv/`, `.env*` are gitignored. A few old sample outputs are tracked; do not add new generated files.
- `.gitignore` has `/test_*.py` (root scratch scripts only); real tests live in `tests/`.
- On the dev PC the default Python is 3.14; use a 3.12 venv (`py -3.12 -m venv .venv`). CI uses 3.12.
- `derive_dcf_inputs` expects specific column names; check `data/normalized/*` headers before trusting DCF inputs.
- JS: `new Date('YYYY-MM-DD')` is UTC midnight; parse date-only strings as local time.
- AI agents and bots: open a PR and check the Vercel preview before merging. Do not merge straight to `main`.

## Conventions
- Commit and push only as the DogInfantry GitHub identity (repo-local `git config`). No AI co-author trailers or "generated with" footers.
- No em dashes in commits, PRs, docs or UI copy.
- Shortest working diff; reuse existing helpers before adding new code; one runnable check for non-trivial logic.
