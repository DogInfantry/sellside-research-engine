# CLAUDE.md

Shared project notes for anyone (human or AI assistant) working in this repo. Keep it to durable facts: architecture, file map, gotchas.

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
- One valuation path: `trg_workbench/pipeline_v2.py::value_ticker()` is used by both the report and the dashboard export, and `value_bank()` covers banks, brokers and insurers (residual income). Do not reimplement DCF logic elsewhere.
- Deploys: the Vercel Git integration deploys every push to `main` and a preview for every PR. There is no deploy workflow (the old token-based one was removed).
- Data refresh: `.github/workflows/refresh-data.yml` runs weekdays at 22:00 UTC (plus manual dispatch). It fetches, exports, validates the JSON strictly, and commits `dashboard_data.json` as github-actions[bot] only if it changed. That push triggers the deploy.

## File Map
| Path | Role |
|---|---|
| `main_v2.py` | CLI: `fetch-all`, `build-report`, `build-all`, `--dry-run` checks |
| `trg_workbench/pipeline_v2.py` | Orchestration: `fetch_data_v2`, `value_ticker`, `value_bank`, `build_research_report_v2`, `_load_*` helpers |
| `trg_workbench/pipeline.py` | v1 fetch (market, SEC, ECB), called by v2 |
| `trg_workbench/analytics/screening.py` | `build_research_dataset` (factor scores 0..1, analyst targets, earnings dates), `top_screen_candidates` |
| `trg_workbench/analytics/valuation.py` | `derive_dcf_inputs`, `scenario_analysis`, `dcf_sensitivity`, `reverse_dcf`, `football_field`, `build_comps_table` (peer multiples from the security master) |
| `trg_workbench/analytics/risk.py` | `build_risk_table` (vol, beta, Sharpe, Sortino, drawdown, VaR/CVaR 1d) |
| `trg_workbench/analytics/summaries.py` | `build_catalyst_calendar` and report summaries |
| `trg_workbench/llm/` | Transcript fetch + heuristic commentary (`build_management_commentary`) |
| `trg_workbench/reporting/` | Charts, HTML/PDF/Markdown renderers, Jinja templates |
| `trg_workbench/sources/` | Market (yfinance; also writes debt, cash, beta to the security master; `fetch_quarterly` for reported quarters), SEC, ECB, US macro (Yahoo, plus FRED for the 2Y) |
| `export_dashboard_data.py` | Builds `dashboard_data.json` from normalized data |
| `index.html` | Dashboard (single file, JSON loaded at runtime) |
| `vercel.json` | Static build of `index.html` + `dashboard_data.json`, filesystem first, then SPA fallback |
| `tests/` | pytest suite (`pytest -q`), incl. `test_export_dashboard.py` |

## Gotchas
- Keep the legacy `builds` in `vercel.json`. Without it Vercel may auto-detect `requirements.txt` / `main.py` as a Python app. Any new static file the page fetches must be added to `builds`.
- Export writes JSON with `allow_nan=False`. Missing values become `null` and render as `n/a`. Never fill gaps with invented numbers or placeholder text.
- `data/`, `outputs/`, `.venv/`, `.env*` are gitignored. A few old sample outputs are tracked; do not add new generated files.
- `.gitignore` has `/test_*.py` (root scratch scripts only); real tests live in `tests/`.
- Use Python 3.12 (CI does); newer versions may not satisfy `requirements.txt`. Local venv goes in `.venv/`.
- `derive_dcf_inputs` reads snake_case security-master columns (camelCase kept as fallback). Financial Services names get `net_debt = 0` on purpose: bank debt and cash are operating balances.
- DCF inputs: shares come from the security master (`impliedSharesOutstanding`, all share classes; SEC and `sharesOutstanding` count one class for GOOGL/META). Growth is consensus +1y revenue growth (`revenue_growth_next_year`), trailing growth only as fallback. Beta is Blume adjusted. Banks, Capital Markets and Insurance (`BALANCE_SHEET_INDUSTRIES`) get no FCF DCF (`value_ticker` returns None, dashboard shows n/a) and no EV multiples in the comps (their EV is not an enterprise value).
- Benchmarks: the export reads the S&P 500 from `data/cache/us_macro_spx_{as_of}.csv` (written by the macro client during `fetch-all`) as the market column for risk beta and the `benchmarks` series; sector ETFs come from the XL* prices via `SECTOR_ETF` in `export_dashboard_data.py`. `vs_sector` medians come from `build_comps_table` over the whole US universe and exclude the stock itself.
- Yahoo drops single days per series (e.g. 09-22 for XLK and SPX but not XLE). Compare series only on the dates they share: the sector block drops rows with any gap, and the page's `relSeries` filters stock, ETF and S&P together. Counting rows per series gives windows that start on different days.
- Dashboard design system (`index.html`): IBM Plex Sans for labels and prose, IBM Plex Mono with tabular numbers for numbers and tickers. Colors are `:root` tokens (`--t2`/`--t3` pass AA on `--card`); gold marks the selected ticker, green/red carry signal only. 12px minimum font. One `@media (max-width:900px)` rule; wide tables scroll inside their card, never the page. `Chart.defaults.animation=false`, Plotly uses `PLOT_FONT`/`PLOT_BASE`. Missing data is an n/a box or cell, never an empty chart. No em or en dashes in visible copy. Check with `detect.mjs` from the impeccable skill.
- Rates: the DCF WACC uses the live 10Y (`ust_10y`, `^TNX`) and Sharpe/Sortino use the 3M bill (`tbill_3m`, `^IRX`); both fall back to 5.3% if the macro fetch fails. `ust_2y` is the real 2Y from FRED `DGS2` (it used to be `^IRX`), and FRED can lag Yahoo by a day.
- Quarters: Yahoo keeps 4 to 7 quarters, and its balance sheet reaches further back than its income statement. `quarterly_block` lists only income statement quarters and builds TTM from 4 back to back quarters that have revenue and net income.
- JS: `new Date('YYYY-MM-DD')` is UTC midnight; `index.html` appends `T12:00` so dates do not shift a day in US timezones.
- Open a PR for every change and check its Vercel preview before merging, including changes made by bots or AI agents.
