# 🏦 Sell Side Research Engine

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Live Data](https://img.shields.io/badge/data-live%20%2F%20real-brightgreen.svg)](#data-sources)
[![Built for Research](https://img.shields.io/badge/built%20for-equity%20research-navy.svg)](#)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Version](https://img.shields.io/badge/version-v1.4.0-blue.svg)](#changelog)

> An equity research workbench that automates the core sell side analyst loop: live data ingestion, factor screening, DCF valuation, risk analytics, a research note and a live dashboard.

Built as a research workbench and portfolio project for equity researchers, PMs and quants. Every number comes from a live source; missing data shows as n/a, never invented.

**Live dashboard:** [sellside-research-engine.vercel.app](https://sellside-research-engine.vercel.app), refreshed every weekday from the pipeline.

**This project is open to contributions.** Whether you want to add a new data source, improve valuation logic, or build a real LLM reasoning layer, see [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## What It Does

Given the ticker universe in `trg_workbench/config.py` and a date, the engine:

1. **Fetches** fundamentals from SEC EDGAR XBRL, prices and analyst estimates from Yahoo Finance, and macro data from the ECB SDMX API and Yahoo Finance market tickers (`^TNX`, `^TYX`, `^IRX`, `^VIX`, `DX-Y.NYB`, `CL=F`, `GC=F`)
2. **Screens** stocks across valuation, growth, quality and momentum factors, plus a forward view from analyst consensus
3. **Values** top candidates using a bear/base/bull DCF and a **reverse DCF** that solves for the growth rate priced in (top 3 names in the note, top 10 on the dashboard)
4. **Analyzes** cached SEC 8-K earnings exhibits for tone, guidance, risks and catalysts via a **keyword heuristic** (no LLM)
5. **Quantifies risk**: VaR, CVaR, Sharpe/Sortino ratios, volatility, max drawdown, correlation matrices, and 63 day beta vs the S&P 500; the dashboard also shows each stock against its sector ETF and the S&P, its sector peers (comps) and sector ETF rotation
6. **Renders** an HTML research note plus PDF and Markdown, and exports `dashboard_data.json` for the live dashboard

---

## Key Features

### 📊 Research Automation
- Multifactor stock screener: valuation, growth, quality, momentum, plus an analyst consensus forward view
- DCF valuation with CAPM based WACC and bear/base/bull scenarios; football field chart on the dashboard. A WACC × terminal growth matrix is computed but not displayed yet
- **Reverse DCF**: solves for the constant 10 year FCF growth rate implied by the current price (FCF proxy = net income × 0.8)
- Earnings date calendar (Yahoo Finance) on the dashboard
- Optional discretionary analyst overlays via CSV (thesis, conviction, catalysts, risks, client angle). They apply only to the v1 `main.py` daily/weekly reports; the v2 note and the dashboard ignore them
- Peer comps on the dashboard: forward P/E, EV/EBITDA, EV/Sales, PEG, FCF yield, growth, margin, ROE and net debt/EBITDA against the median of the stock's sector peers in the 21 stock universe (`build_comps_table`). EV multiples are n/a for banks, brokers and insurers. Historical multiple bands are planned ([#24](https://github.com/DogInfantry/sellside-research-engine/issues/24))

### 🖥️ Live Dashboard
- Static `index.html` (vanilla JS, Chart.js 4.4.1 and Plotly 2.26 from cdnjs) that fetches `dashboard_data.json` at runtime, hosted on Vercel
- Top 10 names by research score: price, 6 month price chart, factor radar, risk metrics, DCF football field (bear/base/bull)
- Rating derived from consensus target upside: BUY above +10%, SELL below -10%, HOLD in between
- Reverse DCF verdict: market implied FCF growth vs consensus +1y revenue growth (STRETCHED / DISCOUNT), plus an implied growth grid across WACC (±2pp) and terminal growth (1.5% to 3.0%)
- Correlation matrix of the names shown, macro snapshot, and upcoming earnings dates
- Three sections behind a sticky Company | Peers | Sector nav (plain anchors, no tab JS)
- Peers: comps table vs the sector peer median, forward P/E vs consensus revenue growth with a least squares line, risk vs return, and factor scores for the whole universe
- Sector: sector ETF returns (1D to YTD) next to the S&P 500, a rotation view (each ETF vs the S&P, 3M to 1M ago against the last month), and each stock's 3M return against its own sector ETF
- Management commentary panel: empty on the live site, because CI has no cached transcripts, so every ticker shows "n/a: no cached earnings call transcript"

### 🎙️ Management Commentary (keyword heuristic)
- Parses SEC 8-K earnings exhibits from a local cache (`data/cache/transcripts/TICKER_latest.txt`); set `TRG_FETCH_TRANSCRIPTS=1` to fetch from EDGAR when building the note
- Outputs a keyword tone score, one guidance sentence, up to 3 risk and 3 catalyst sentences, and a Q&A tone label
- No LLM calls: chunks are ranked and sentences picked by keyword counts

### 🔄 Reverse DCF
- Given the current price, WACC and terminal growth, solves for the constant 10 year FCF growth rate the market is pricing in
- Note: implied growth at the base WACC and at WACC ±100bps (fixed terminal growth)
- Dashboard: compares market implied FCF growth with consensus +1y revenue growth (STRETCHED / DISCOUNT) and shows a WACC × terminal growth grid

### 🔌 Data Integration (No Synthetic Data)

| Source | Coverage |
|--------|----------|
| **SEC EDGAR XBRL** | US fundamentals (revenue, net income, equity), audited |
| **Yahoo Finance** | Prices, security master (shares, debt, cash, beta), EPS and revenue estimates, analyst recommendations, price targets, earnings dates |
| **ECB SDMX API** | European interest rates, EUR/USD FX |
| **US Macro (Yahoo Finance)** | 3M T-bill (`^IRX`), 10Y (`^TNX`) and 30Y (`^TYX`) yields, VIX, DXY, WTI, gold, S&P 500, Nasdaq 100 |

Missing values are written to `dashboard_data.json` as `null` (`allow_nan=False`) and render as n/a. Gaps are never filled with invented numbers.

Known data gaps:
- There is no 2 year Treasury series yet: the dashboard shows the 13 week T-bill (`^IRX`) and a 3M/10Y spread, labeled as such
- The note's correlation heatmap drops tickers starting with "X" (so XOM) through the ETF filter in `charts.py`

### 📁 Outputs
- **HTML Research Note**: navy/gold template with 12 section slots. The v2 pipeline currently fills sector performance, risk analytics (correlation heatmap), valuation (DCF scenarios and reverse DCF) and management commentary when transcripts are cached. The other sections (executive summary, macro, ECB, screen, stock highlights, catalyst calendar, tactical takeaways, analyst overlays) are not wired yet
- **PDF Export**: WeasyPrint rendering; falls back to HTML output when WeasyPrint is unavailable
- **Markdown Note**: sector moves, reverse DCF results and commentary (top picks, macro and catalysts only via v1 `main.py`)
- **PNG Charts** (150 DPI) in `outputs/charts/`: sector heatmap, screen scores, correlation heatmap, macro dashboard, and per ticker price, return distribution and factor radar
- **Dashboard JSON**: `dashboard_data.json`, read by the live dashboard

### ⚙️ CLI
- `--dry-run` checks the date, `SEC_USER_AGENT`, the output dir and the WeasyPrint/Plotly installs without fetching data
- `--quiet` hides progress bars
- `--formats html,pdf,markdown` picks the report outputs (`build-report`, `build-all`)
- `tqdm` progress bars on report build stages (valuation, charts, PDF)

---

## Quick Start

```bash
git clone https://github.com/DogInfantry/sellside-research-engine.git
cd sellside-research-engine
python -m venv .venv                # Python 3.12 (what CI uses)
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Set SEC user agent (API etiquette)
export SEC_USER_AGENT="Your Name your_email@example.com"

# Fetch data + build the research note in one command
python main_v2.py build-all --as-of 2026-04-12

# Check setup without fetching data
python main_v2.py build-all --as-of 2026-04-12 --dry-run

# Hide progress bars
python main_v2.py build-all --as-of 2026-04-12 --quiet
```

Outputs to `outputs/`:
- `research_note_2026-04-12.html`
- `research_note_2026-04-12.pdf`
- `daily_note_2026-04-12.md`

Dashboard data:

```bash
python main_v2.py fetch-all --as-of 2026-04-12
python export_dashboard_data.py --as-of 2026-04-12 --skip-fetch   # without --skip-fetch it fetches first
python -m http.server                                             # then open http://localhost:8000
```

The v1 CLI `main.py` (`fetch-data`, `build-daily`, `build-weekly`, `build-kpis`) still exists. It is the only path that reads `data/analyst_views.csv` and fills the full daily/weekly templates (top picks, macro, catalysts).

---

## Architecture

```
python main_v2.py fetch-all --as-of D                   -> data/normalized/*_D.csv (gitignored)
python export_dashboard_data.py --as-of D --skip-fetch  -> dashboard_data.json (committed)
index.html fetch('dashboard_data.json')                 -> dashboard
python main_v2.py build-report --as-of D                -> outputs/research_note_D.html (+ PDF, Markdown)
```

One valuation path: `pipeline_v2.value_ticker()` is shared by the research note (top 3 names) and the dashboard (top 10 names). Do not reimplement DCF logic elsewhere.

```
sellside-research-engine/
├── main_v2.py                          # CLI: fetch-all | build-report | build-all | --dry-run | --quiet
├── main.py                             # v1 CLI: daily/weekly/KPI reports, analyst overlays
├── export_dashboard_data.py            # Normalized CSVs → dashboard_data.json
├── index.html                          # Dashboard (single file, JSON loaded at runtime)
├── dashboard_data.json                 # Dashboard data, refreshed by CI
├── vercel.json                         # Static build of index.html + dashboard_data.json
├── .github/workflows/refresh-data.yml  # Weekday data refresh
├── trg_workbench/
│   ├── config.py                       # Universe (DEFAULT_US_TICKERS), sector ETFs, paths
│   ├── pipeline.py                     # v1 fetch (market, SEC, ECB), called by v2
│   ├── pipeline_v2.py                  # fetch_data_v2, value_ticker, build_research_report_v2
│   ├── sources/
│   │   ├── sec.py                      # SEC EDGAR XBRL companyfacts
│   │   ├── ecb.py                      # ECB SDMX API client
│   │   ├── macro_us.py                 # US macro via Yahoo Finance tickers
│   │   └── market.py                   # Yahoo Finance prices, security master, estimates
│   ├── analytics/
│   │   ├── screening.py                # Factor scores and research ranking
│   │   ├── valuation.py                # WACC, DCF scenarios, sensitivity, reverse DCF, football field
│   │   ├── risk.py                     # Vol, beta, Sharpe, Sortino, drawdown, VaR/CVaR
│   │   ├── summaries.py                # Catalyst calendar, sector and macro summaries
│   │   └── kpis.py                     # KPI report context
│   ├── llm/                            # Keyword heuristic, no LLM calls
│   │   ├── transcript_fetcher.py       # SEC 8-K earnings exhibits, cached locally
│   │   ├── chunker.py, retriever.py    # Chunking and keyword ranking
│   │   └── reasoner.py, pipeline.py    # Tone, guidance, risk and catalyst extraction
│   └── reporting/
│       ├── charts.py                   # 12 chart functions (150 DPI), 8 called for the note
│       ├── pdf_renderer.py             # Jinja2 → HTML → PDF (HTML fallback)
│       ├── renderers.py                # Template rendering
│       └── templates/                  # research_note.html.j2, daily_note.md.j2, weekly_wrap.md.j2, kpi_report.html.j2
├── tests/                              # pytest suite
├── data/
│   ├── analyst_views_template.csv      # Discretionary analyst overlay template
│   └── cache/, normalized/             # Cached and normalized data (gitignored)
└── outputs/                            # Generated notes, PDFs, charts (gitignored)
```

### Refresh and deploy
- **Weekday refresh**: `.github/workflows/refresh-data.yml` runs weekdays at 22:00 UTC (cron `0 22 * * 1-5`) and on manual dispatch, on Python 3.12. It runs `fetch-all`, then `export_dashboard_data.py --skip-fetch`, validates the JSON, and commits `dashboard_data.json` as `github-actions[bot]` only when it changed. That push triggers the Vercel deploy.
- **Deploys**: the Vercel Git integration deploys every push to `main` and builds a preview for every PR. Keep the legacy `builds` list in `vercel.json` (`index.html` + `dashboard_data.json`) so Vercel does not detect a Python app.

---

## Screening Model

| Factor | Signals | Weight |
|--------|---------|--------|
| **Valuation** | P/S, P/E, percentile ranked (lower is better) | 25% |
| **Growth** | Trailing YoY revenue growth (SEC) | 25% |
| **Quality** | Net margin, ROE | 25% |
| **Momentum** | 1M and 3M returns | 25% |

The composite score is the equal weighted mean of the four factors. A second pass **Forward View** scores forward EPS growth, consensus target upside, the analyst buy ratio and its 3 month change. The research score averages the composite, forward and discretionary (CSV overlay, v1 only) scores.

---

## DCF & Reverse DCF Valuation

**Standard DCF inputs:**
- FCF proxy = SEC net income (Yahoo fallback) × 0.80
- **WACC** = E/V × (5.3% + Blume adjusted β × 5.5%) + D/V × 6% × (1 - 21%), with D/E fixed at 0.30. These are fixed defaults, not live Treasury yields
- Blume adjusted beta = 0.67 × raw Yahoo beta + 0.33
- Growth = consensus +1y revenue growth (`revenue_growth_next_year`), trailing growth only as fallback, clamped to the range -20% to 50%
- Shares from the security master (`impliedSharesOutstanding`, all share classes; SEC dei counts one class for GOOGL/META)
- Financial Services names get net debt = 0 (bank debt and cash are operating balances). Banks, Capital Markets and Insurance get no FCF DCF: `value_ticker` returns None and the dashboard shows n/a (JPM and JEF in the current data)
- 3 scenarios: Bear (growth × 0.7, TGR 1%, WACC +1pp), Base (TGR 2.5%), Bull (growth × 1.3, TGR 3.5%, WACC -0.5pp)
- Sensitivity matrix: WACC 7% to 12% × terminal growth 1% to 4%, computed but not displayed yet
- Output: intrinsic value per share for each scenario, with the WACC and TGR used

**Reverse DCF:**
- Inputs: current market price, base WACC, base terminal growth, FCF proxy, net debt, shares
- Solves: the constant 10 year FCF growth rate priced in by the market
- Output: implied growth at WACC ±100bps in the note; consensus comparison and WACC × terminal growth grid on the dashboard

---

## Management Commentary

The commentary module (`trg_workbench/llm/`) is a keyword heuristic over SEC 8-K earnings exhibits. It does not call an LLM.

- **Tone score**: positive / (positive + negative) keyword counts
- **Q&A tone**: constructive / balanced / cautious (score >= 0.60 / between / <= 0.40)
- **Guidance**: one verbatim sentence selected by guidance keywords
- **Risk flags**: up to 3 sentences containing generic risk words (risk, headwind, pressure, decline, and similar)
- **Catalyst flags**: up to 3 sentences mentioning launches, buybacks, approvals, partnerships

The note writes the results to `data/normalized/management_commentary_{date}.json` and renders them when transcripts are cached.

---

## Risk Metrics

VaR (95%, 1D) · CVaR · Beta · Volatility (21D/63D) · Sharpe Ratio · Sortino Ratio · Max Drawdown · Spearman Correlation Matrix

- The risk table is shown on the dashboard. The note reads `risk_metrics_{date}.csv`, which nothing writes yet, so its risk table does not render
- Dashboard beta is 63 day OLS vs the S&P 500 (`^GSPC`, cached by the macro client); WACC uses the Blume adjusted Yahoo beta instead
- Sharpe and Sortino use a fixed 5.3% risk free rate
- Spearman correlation drives the note heatmap; the dashboard matrix is Pearson on 63 days of daily returns

---

## Customization

**Change the universe**: edit `DEFAULT_US_TICKERS` in `trg_workbench/config.py`

**Adjust factor weights**: factors are equally weighted; change the `.mean(axis=1)` in `build_research_dataset` (`trg_workbench/analytics/screening.py`) to weight them

**Override DCF assumptions**: edit the `estimate_wacc` defaults in `trg_workbench/analytics/valuation.py` (`risk_free_rate`, `equity_risk_premium`, `tax_rate`, `debt_to_equity`, `cost_of_debt`) and the scenario TGRs in `scenario_analysis`

**Add analyst views** (v1 `main.py` reports only): copy `data/analyst_views_template.csv` to `data/analyst_views.csv` and populate the discretionary overlay fields:

| Column | Type | Valid Values / Example | Description |
|--------|------|------------------------|-------------|
| `ticker` | string | `AAPL` | Stock ticker, matched case insensitively against the research universe. |
| `stance` | string | `Buy`, `Hold`, `Sell`, `Overweight`, `Underweight`, `Positive`, `Negative`, `Neutral` | Analyst rating used in discretionary scoring. |
| `conviction` | number | `1` to `5` (`5` = highest conviction) | Analyst conviction score; the screening model normalizes this by dividing by 5. |
| `thesis` | string | `Services mix supports margin expansion` | Core investment thesis. |
| `catalyst` | string | `June WWDC AI updates` | Near term upside or event catalyst. |
| `risk` | string | `China demand weakness` | Key downside risk or debate. |
| `client_angle` | string | `High-quality mega-cap defensiveness with AI optionality` | Client specific framing for the callout section. |
| `management_access_note` | string | `Investor meetings requested after earnings` | Management access or meeting context for research notes. |

Example:

```csv
ticker,stance,conviction,thesis,catalyst,risk,client_angle,management_access_note
AAPL,Buy,4,"Services mix supports margin expansion","June WWDC AI updates","China demand weakness","High-quality mega-cap defensiveness with AI optionality","Investor meetings requested after earnings"
```

---

## Testing

```bash
pytest -q
```

Covers: SEC XBRL metric extraction · ECB normalization · price snapshot and screening · template rendering · factor radar chart · transcript chunking, retrieval and commentary extraction · reverse DCF solver · DCF inputs · bank exclusion · dashboard JSON export · KPI report

There is no pytest CI yet ([#4](https://github.com/DogInfantry/sellside-research-engine/issues/4)); the only workflow is the data refresh.

---

## 🤝 Contributing

Contributions are welcome from equity researchers, quants, data engineers, and Python developers. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, PR guidelines, and how to find good first issues.

Open a PR for every change and check its Vercel preview before merging, including changes made by bots or AI agents.

For questions or ideas, open a [Discussion](https://github.com/DogInfantry/sellside-research-engine/discussions) or comment on an issue.

---

## Roadmap

Items marked 🟢 are open issues ready to be picked up. See the [Issues tab](https://github.com/DogInfantry/sellside-research-engine/issues) for full specs and acceptance criteria.

---

### 🏁 Milestone: v1.4, Depth & Credibility

> Make the research note defensible. These close the largest credibility gaps between a sophisticated demo and an institutional grade engine.

#### Fundamentals & Filings
- 🟢 [10-K/10-Q Filings Intelligence: MD&A parser, risk factor change detection, segment extraction](https://github.com/DogInfantry/sellside-research-engine/issues/19)
- 🟢 [Estimate & revision layer: consensus revision tracking, surprise history, target price drift](https://github.com/DogInfantry/sellside-research-engine/issues/20)
- 🟢 [Insider / Form 4 parser: management buy/sell signals from SEC filings](https://github.com/DogInfantry/sellside-research-engine/issues/25)
- 🟢 [FRED API connector: CPI, PCE, credit spreads, yield curve](https://github.com/DogInfantry/sellside-research-engine/issues/8)

#### Valuation Engine
- 🟢 [Monte Carlo DCF + EV bridge: scenario engine with sector specific assumption packs](https://github.com/DogInfantry/sellside-research-engine/issues/23)
- 🟢 [Peer dashboard & CCA upgrade: historical multiples, percentile bands, peer rerating analysis](https://github.com/DogInfantry/sellside-research-engine/issues/24)
- 🟢 [Piotroski F-Score and Altman Z-Score in screening model](https://github.com/DogInfantry/sellside-research-engine/issues/7)

#### Output & Auditability
- 🟢 [Executive summary page: six field note header (rating, target, variant view, thesis, risks, catalyst)](https://github.com/DogInfantry/sellside-research-engine/issues/21)
- 🟢 [Audit trail panel: source, timestamp, and assumption provenance for every key claim](https://github.com/DogInfantry/sellside-research-engine/issues/22)
- 🟢 ["What changed since last note" delta blocks: versioned thesis, target, estimate, and risk diffs](https://github.com/DogInfantry/sellside-research-engine/issues/26)
- [Interactive HTML report with Plotly charts](https://github.com/DogInfantry/sellside-research-engine/issues/10) (closed: Plotly mode exists in `charts.py`, but the note still renders static PNGs)

---

### 🏗️ Milestone: v1.5, Infrastructure & Packaging

> Make the repo look built, not hacked. These don't add features; they make every existing feature credible to a technical reviewer.

- 🟢 [GitHub Actions CI: run pytest on every PR automatically](https://github.com/DogInfantry/sellside-research-engine/issues/4)
- 🟢 [Docker + docker-compose for reproducible execution](https://github.com/DogInfantry/sellside-research-engine/issues/11)
- 🟢 [config.yaml: replace direct Python file editing for watchlists, weights, and output preferences](https://github.com/DogInfantry/sellside-research-engine/issues/27)
- 🟢 [Integration tests with mocked APIs: fixture based test coverage for SEC, Yahoo, FRED](https://github.com/DogInfantry/sellside-research-engine/issues/28)
- 🟢 [Sample notebooks + prerendered demo artifacts: zero friction portfolio preview](https://github.com/DogInfantry/sellside-research-engine/issues/29)
- 🟢 [Unit tests for `build_catalyst_calendar` (`analytics/summaries.py`)](https://github.com/DogInfantry/sellside-research-engine/issues/2)

---

### 🔭 Backlog

#### Analytics
- [ ] Forward multiples in CCA (NTM EV/EBITDA, forward P/E)
- [ ] LBO model stub: entry/exit with sponsor IRR
- [ ] Event study module: abnormal returns around earnings and macro catalysts
- [ ] Ranking explainability layer: factor attribution and sensitivity for screener output

#### Data Sources
- [ ] OpenBB Platform SDK as optional aggregated source layer
- [ ] SEDAR+ / Companies House for Canadian and UK filings
- [ ] News catalyst detection: map headlines to catalyst calendar

#### Reporting
- 🟢 [PowerPoint export (`python-pptx`) matching GS/JPM slide deck format](https://github.com/DogInfantry/sellside-research-engine/issues/32)
- [ ] Excel DCF model export (`openpyxl`) with live formula links
- [ ] Streamlit dashboard comparing multiple tickers

#### Engineering
- [ ] Async data fetching (`asyncio` + `aiohttp`) to parallelise source calls
- [ ] Redis backed caching layer with TTL invalidation
- [ ] Pluggable LLM backend (OpenAI / local Ollama / Mistral) to replace the keyword heuristic

> Want to tackle a backlog item? Open an issue to discuss scope before building.

---

## Changelog

### Since v1.4.0
- **feat**: Dashboard connected to live pipeline data via `export_dashboard_data.py`, plus the weekday refresh workflow ([#50](https://github.com/DogInfantry/sellside-research-engine/pull/50))
- **fix**: DCF inputs: all share classes from the security master, consensus +1y revenue growth, Blume adjusted beta, no FCF DCF for banks, capital markets and insurance ([#55](https://github.com/DogInfantry/sellside-research-engine/pull/55))
- **fix**: `derive_dcf_inputs` reads snake_case security master columns ([#52](https://github.com/DogInfantry/sellside-research-engine/pull/52))
- **fix**: Note sector heatmap and factor radar ([#56](https://github.com/DogInfantry/sellside-research-engine/pull/56))
- **fix**: Dashboard dates no longer shift a day in US timezones ([#51](https://github.com/DogInfantry/sellside-research-engine/pull/51))
- **ci**: Token based Vercel deploy workflow removed; the Vercel Git integration deploys `main` and PR previews

### v1.4.0, June 1, 2026
- **feat**: Research dashboard (`index.html`) with DCF, reverse DCF, factor screener and risk analytics, deployed on Vercel
- **feat**: Plotly chart mode in `charts.py` ([#10](https://github.com/DogInfantry/sellside-research-engine/issues/10)); the note still uses static PNGs
- **docs**: Roadmap with v1.4 and v1.5 milestone issues (#19 to #29)
- **license**: Switched from MIT to Apache 2.0, with a NOTICE file

### v1.3.0, April 12, 2026
- **feat**: Reverse DCF analytics: solves for the implied FCF growth rate from the current market price, with WACC ±100bps sensitivity
- **feat**: Management commentary MVP: keyword heuristic transcript parser (tone score, guidance sentence, risk/catalyst sentences)
- **feat**: `--dry-run` CLI flag for setup checks without fetching data
- **feat**: `--quiet` mode and `tqdm` progress bars on report build stages
- **feat**: HTML fallback when WeasyPrint is unavailable
- **docs**: Analyst views schema documented

### v1.2.0, April 11, 2026
- CLI refactor with quiet aware progress bars and automated chart integration
- Session output pipeline: research note, daily brief, session README
- Analyst views schema documentation

### v1.1.0, April 11, 2026
- `--dry-run` and progress bar features merged
- `.gitignore` updated to exclude `outputs/`

---

## License

Apache 2.0. See [LICENSE](LICENSE). Forks and redistributions must keep the [NOTICE](NOTICE) file and credit the original author.

---

## Acknowledgments

Data: SEC EDGAR · Yahoo Finance (yfinance) · ECB SDMX  
Inspiration: Goldman Sachs TRG · JPMorgan Equity Research · Morgan Stanley Research  
Stack: Python · pandas · numpy · scipy · matplotlib · plotly · Jinja2 · WeasyPrint · yfinance · tqdm  
Dashboard: vanilla JS · Chart.js · Plotly · Vercel · GitHub Actions
