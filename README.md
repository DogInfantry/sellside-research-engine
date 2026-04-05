# 🏦 Sell-Side Research Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Live Data](https://img.shields.io/badge/data-live%20%2F%20real-brightgreen.svg)](#data-sources)
[![Built for Research](https://img.shields.io/badge/built%20for-equity%20research-navy.svg)](#)

> A production-grade equity research pipeline that automates the full sell-side analyst workflow — from live data ingestion to institutional-quality research notes.

Mirrors the output standards of **Goldman Sachs Tactical Research Group**, **JPMorgan Equity Research**, and **Morgan Stanley Research**. Built for equity researchers, PMs, and quants who need institutional output at scale.

---

## What It Does

Given a watchlist of tickers and a date, the engine:

1. **Fetches** live fundamentals from SEC EDGAR XBRL, prices from Yahoo Finance, macro data from ECB SDMX + US Treasury feeds
2. **Screens** stocks across valuation, growth, quality, and momentum factors
3. **Values** top candidates using a multi-scenario DCF (bear/base/bull) + comparable company analysis (CCA)
4. **Analyzes risk** — VaR, CVaR, Sharpe/Sortino ratios, beta, max drawdown, correlation matrices
5. **Renders** a 12-section GS-style HTML research note with embedded PNG charts, exported as HTML + PDF + Markdown

---

## Key Features

### 📊 Research Automation
- Multi-factor stock screener — valuation, growth, quality, momentum + analyst consensus overlay
- Automated DCF valuation with CAPM-based WACC, sensitivity matrices (WACC × terminal growth), and football field charts
- Peer comps (CCA) with sector-relative multiples and forward earnings
- Catalyst calendar from market data and public disclosures
- Optional discretionary analyst overlays via CSV (thesis, conviction, catalysts, risks, client angle)

### 🔌 Data Integration (No Synthetic Data)

| Source | Coverage |
|--------|----------|
| **SEC EDGAR XBRL** | US fundamentals (revenue, net income, equity) — audited |
| **Yahoo Finance** | Prices, EPS estimates, analyst recommendations, price targets |
| **ECB SDMX API** | European interest rates, EUR/USD FX |
| **US Macro** | 2Y/10Y/30Y Treasuries, VIX, DXY, WTI crude, gold futures |

### 📁 Professional Outputs
- **HTML Research Note** — 12-section dossier with GS navy/gold branding, embedded charts, scenario analysis
- **PDF Export** — WeasyPrint rendering, print-optimized for client distribution
- **Markdown Daily Note** — Git-friendly summary with top picks, macro snapshot, key changes
- **PNG Charts** (150 DPI) — DCF sensitivity heatmaps, football field, factor radars, correlation matrices, sector heatmaps

---

## Quick Start

```bash
git clone https://github.com/DogInfantry/sellside-research-engine.git
cd sellside-research-engine
pip install -r requirements.txt

# Set SEC user agent (API etiquette)
export SEC_USER_AGENT="Your Name your_email@example.com"

# Fetch data + build full research note in one command
python main_v2.py build-all --as-of 2026-03-27
```

Outputs to `outputs/`:
- `research_note_2026-03-27.html`
- `research_note_2026-03-27.pdf`
- `daily_note_2026-03-27.md`

> **Windows users**: Run from Anaconda Prompt (`conda activate prime_quant`) to avoid matplotlib DLL conflicts with Git Bash.

---

## Architecture

```
sellside-research-engine/
├── main_v2.py                          # CLI: fetch-all | build-report | build-all
├── trg_workbench/
│   ├── sources/
│   │   ├── sec_client.py              # SEC EDGAR XBRL parser
│   │   ├── ecb_client.py              # ECB SDMX API client
│   │   ├── macro_us.py                # US macro snapshot
│   │   └── yfinance_client.py         # Yahoo Finance adapter
│   ├── analytics/
│   │   ├── screening.py               # Multi-factor composite ranking
│   │   ├── valuation.py               # DCF, WACC, peer comps, football field
│   │   ├── risk.py                    # VaR, CVaR, Sharpe, beta, drawdown
│   │   └── catalyst.py                # Catalyst calendar builder
│   ├── reporting/
│   │   ├── charts.py                  # 12 PNG chart generators (GS palette, 150 DPI)
│   │   ├── pdf_renderer.py            # Jinja2 → HTML → PDF
│   │   └── templates/
│   │       └── research_note.html.j2  # 12-section GS-style HTML template
│   └── pipeline_v2.py                 # Full pipeline orchestration
├── data/
│   ├── analyst_views_template.csv     # Discretionary analyst overlay template
│   └── cache/                         # Cached fundamentals, prices, macro
└── outputs/                           # Generated research notes, PDFs, charts
```

---

## Screening Model

| Factor | Signals | Weight |
|--------|---------|--------|
| **Valuation** | P/S, P/E — percentile ranked | 30% |
| **Growth** | Trailing + forward revenue/EPS growth | 25% |
| **Quality** | Net margin, ROE, Debt/Equity | 25% |
| **Momentum** | 1M, 3M, YTD price returns | 20% |

A second-pass **Forward View** layers in analyst consensus, price target upside, and earnings revision trends. Optional CSV overlays add discretionary conviction scoring.

---

## DCF Valuation Inputs

- **Free cash flow** from SEC EDGAR XBRL
- **WACC** = Risk-free rate (10Y UST) + β × 5% market risk premium − tax shield
- **3 scenarios**: Bear (conservative growth), Base (consensus), Bull (upside case)
- **Sensitivity matrix**: WACC × Terminal Growth Rate
- **Output**: Intrinsic value per share + implied upside/downside to current price

---

## Risk Metrics

VaR (95%, 1D) · CVaR · Beta · Volatility (21D/63D) · Sharpe Ratio · Sortino Ratio · Max Drawdown · Spearman Correlation Matrix

---

## Customization

**Change watchlist** — edit `WATCHLIST` in `trg_workbench/pipeline_v2.py`

**Adjust factor weights** — edit `WEIGHTS` in `trg_workbench/analytics/screening.py`

**Override DCF assumptions** — edit `valuation.py` (rfr, market_risk_premium, terminal_growth_rate, tax_rate)

**Add analyst views** — populate `data/analyst_views.csv` with stance, conviction, thesis, catalyst, risk, client_angle

---

## Testing

```bash
pytest
```

Covers: SEC XBRL parsing · ECB normalization · screening logic · template rendering · risk analytics · chart generation

---

## Roadmap

- [ ] Real-time price streaming (WebSocket)
- [ ] Options analytics (IV surface, Greeks)
- [ ] LLM-powered investment narrative generation
- [ ] Sector rotation dashboard
- [ ] Bloomberg API integration
- [ ] Interactive Streamlit research collaboration app

---

## License

MIT — free to use, modify, and distribute. See [LICENSE](LICENSE).

---

## Acknowledgments

Data: SEC EDGAR · Yahoo Finance · ECB SDMX · yfinance
Inspiration: Goldman Sachs TRG · JPMorgan Equity Research · Morgan Stanley Research
Stack: Python · matplotlib · seaborn · WeasyPrint · Jinja2 · pandas · yfinance
