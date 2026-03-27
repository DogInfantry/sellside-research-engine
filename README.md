# Sell-Side Research Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Real Data](https://img.shields.io/badge/data-live%20%2F%20real-brightgreen.svg)](#data-sources)

A production-grade equity research pipeline that ingests live financial data, performs multi-factor stock screening, generates valuations, and publishes professional research deliverables in HTML, PDF, and Markdown formats.

Built for sell-side analysts, portfolio managers, and quantitative researchers who need institutional-quality research output at scale. Mirrors the workflow and output standards of top-tier research groups (Goldman Sachs Tactical Research Group, JPMorgan, Morgan Stanley).

---

## Table of Contents

- [Key Features](#key-features)
- [Data Sources](#data-sources)
- [Output Formats](#output-formats)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Analytical Capabilities](#analytical-capabilities)
- [Configuration](#configuration)
- [Running the Pipeline](#running-the-pipeline)
- [Output Files](#output-files)
- [Customization](#customization)
- [Testing](#testing)
- [License](#license)

---

## Key Features

### Research Automation
- **Multi-factor stock screening**: Valuation, growth, quality, momentum, and forward-looking metrics
- **Automated DCF valuation**: CAPM-based WACC, multi-stage cash flow projection, bear/base/bull scenarios, sensitivity matrices
- **Risk analytics**: VaR, CVaR, Sharpe ratio, Sortino ratio, maximum drawdown, correlation matrices, beta calculation
- **Peer comparison tables**: Sector-relative multiples, forward earnings consensus
- **Catalyst calendar**: Event-driven equity catalysts extracted from market data and public disclosures

### Data Integration
- **Real live data**: SEC EDGAR (fundamentals), Yahoo Finance (market prices, earnings estimates), ECB SDMX (macro)
- **No synthetic data**: All outputs reflect actual market conditions and company metrics
- **Enterprise-grade sources**: Direct APIs with error handling, retry logic, and data validation
- **Global macro context**: US Treasury yields, volatility (VIX), equity indices, commodity prices, FX (DXY), ECB rates

### Professional Output
- **12-section HTML research note**: GS-style with navy/gold branding, embedded charts, callout cards, scenario analysis
- **PDF export**: WeasyPrint rendering with graceful HTML fallback
- **Markdown daily note**: Git-friendly, portable format for internal distribution
- **High-quality PNG charts** (150 DPI): DCF sensitivity heatmaps, football field valuations, factor radars, correlation matrices, sector heatmaps, price charts with moving averages

### Analyst Workflow
- **Discretionary overlays**: Optional CSV input for analyst stance, conviction, thesis, catalysts, risks, and client angles
- **Templated commentary**: Jinja2-based rendering with automatic metric formatting and narrative generation
- **Deterministic ranking**: Multi-level scoring (fundamental screen → forward view → discretionary conviction)
- **Scalable to watchlists**: Generate research on 50+ stocks with full analytical depth

---

## Data Sources

| Source | Coverage | Frequency | Quality |
|--------|----------|-----------|---------|
| **SEC EDGAR XBRL** | US public company fundamentals (revenue, net income, shareholders' equity) | Quarterly + annual | Audited, authoritative |
| **Yahoo Finance** | End-of-day prices, earnings estimates, analyst recommendations, price targets | Daily | Real-time market consensus |
| **ECB SDMX API** | European interest rates (main refinancing rate, deposit facility rate), FX (EUR/USD) | Daily | Official policy data |
| **Yahoo Finance Indices** | US equity indices (S&P 500, Nasdaq-100), sector ETFs, VIX, Treasury yields | Daily | Market consensus |
| **US Macro Indicators** | 2Y/10Y/30Y Treasury rates, DXY, crude oil (WTI), gold futures, curve spread | Daily | Live market data |

**Data Integrity Notes:**
- No proprietary Bloomberg, FactSet, or Datastream feeds (not replicable for free/open source)
- Yahoo Finance is convenient for research workflows; it is not official exchange data. Caveats are documented.
- SEC EDGAR is the authoritative source for US fundamentals; Yahoo fallback is used only when SEC blocks requests.
- All sources are public, no synthetic or hand-made investment data is used.

---

## Output Formats

### 1. **HTML Research Note** (12 Sections)
A complete, printable research dossier with embedded charts and professional styling:
- Executive Summary & Investment Thesis
- US Macro Snapshot (yields, VIX, sentiment indicators)
- Europe Macro & ECB Context
- Sector Performance Tape & Heatmaps
- Risk Analytics Dashboard
- Stock Screen Results & Leader Cards
- Per-Stock Deep Dives:
  - Price chart with 50/200-day moving averages
  - DCF valuation (base, bull, bear scenarios)
  - Comps table (sector-relative multiples)
  - Risk metrics (volatility, beta, Sharpe ratio)
  - Factor radar chart (valuation, growth, quality, momentum)
- DCF Scenario Analysis & Sensitivity Matrices
- Catalyst Calendar
- Tactical Takeaways & Call Summary
- Disclosures & Data Attribution

### 2. **PDF Export**
HTML rendered to PDF via WeasyPrint with page breaks and print optimization.
- Professional layouts suitable for client distribution
- Embedded charts and tables
- Graceful fallback to HTML if PDF generation fails

### 3. **Markdown Daily Note**
Lightweight, version-control-friendly format:
- Top stock picks with ratings and targets
- Macro summary
- Key data points and changes
- Suitable for Slack, email, or Git documentation

---

## Quick Start

### Prerequisites
- Python 3.10+
- pip or conda
- (Optional) Anaconda/Miniconda for isolated environment

### Installation

Clone the repository:
```bash
git clone https://github.com/DogInfantry/sellside-research-engine.git
cd sellside-research-engine
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Or with conda:
```bash
conda env create -f environment.yml
conda activate prime_quant
```

### Set SEC User Agent (Best Practice)
Before running live data fetches, set your SEC user agent to identify your requests:

```bash
export SEC_USER_AGENT="Your Name your_email@example.com"
```

Or on Windows PowerShell:
```powershell
$env:SEC_USER_AGENT = "Your Name your_email@example.com"
```

### Generate Research (One Command)
```bash
python main_v2.py build-all --as-of 2026-03-27
```

This generates:
- `outputs/research_note_2026-03-27.html` (full GS-style note with charts)
- `outputs/research_note_2026-03-27.pdf` (if WeasyPrint is available)
- `outputs/daily_note_2026-03-27.md` (summary markdown)

---

## Architecture

```
sellside-research-engine/
├── main_v2.py                              # CLI entry point (fetch-all, build-report, build-all)
├── requirements.txt                        # Python dependencies
├── trg_workbench/
│   ├── sources/
│   │   ├── sec_client.py                  # SEC EDGAR XBRL parser
│   │   ├── ecb_client.py                  # ECB SDMX API client
│   │   ├── macro_us.py                    # US macro snapshot (yields, VIX, FX, commodities)
│   │   └── yfinance_client.py             # Yahoo Finance price/estimate/recommendation adapter
│   ├── analytics/
│   │   ├── screening.py                   # Multi-factor stock ranking
│   │   ├── valuation.py                   # DCF, WACC, peer comps, football field
│   │   ├── risk.py                        # Risk metrics (VaR, CVaR, Sharpe, beta, correlation)
│   │   └── catalyst.py                    # Event calendar builder
│   ├── reporting/
│   │   ├── charts.py                      # 12 PNG chart generators (150 DPI, GS palette)
│   │   ├── pdf_renderer.py                # Jinja2 → HTML → PDF/HTML output
│   │   ├── templates/
│   │   │   └── research_note.html.j2      # 12-section GS-style HTML template
│   │   └── write_report.py                # Output file management
│   └── pipeline_v2.py                     # Orchestration (fetch → build research → render output)
├── outputs/                               # Generated research notes, PDFs, charts
├── data/
│   ├── analyst_views_template.csv         # Template for discretionary analyst overlays
│   └── cache/                             # Cached data (fundamentals, prices, macro)
└── LICENSE                                # MIT License
```

### Key Classes & Functions

**Sources** (`trg_workbench/sources/`):
- `SECClient`: Fetches company facts (revenue, net income, shares) from SEC EDGAR XBRL
- `ECBClient`: Pulls ECB interest rates and FX from SDMX CSV API
- `USMacroClient`: Builds US macro snapshot (yields, VIX, DXY, commodities)
- `YFinanceClient`: Wraps yfinance for prices, estimates, recommendations

**Analytics** (`trg_workbench/analytics/`):
- `build_research_dataset()`: Merges fundamentals, prices, metadata into scoring-ready DataFrame
- `build_screening_model()`: Composite ranking (valuation + growth + quality + momentum)
- `derive_dcf_inputs()`: Extract WACC and terminal growth assumptions from data
- `dcf_valuation()`: Base/bull/bear intrinsic value per share
- `build_risk_table()`: Vol, beta, Sharpe, Sortino, VaR, CVaR, max drawdown
- `build_catalyst_calendar()`: Event-driven opportunities

**Reporting** (`trg_workbench/reporting/`):
- `build_research_charts()`: Generates 12 PNG chart types
- `render_research_note_pdf()`: Jinja2 render → PDF/HTML
- `build_jinja_env()`: Custom filters (pct, dollar, img_b64, signed_pct)

**Pipeline** (`trg_workbench/pipeline_v2.py`):
- `fetch_data_v2()`: Download and cache latest fundamentals, prices, macro
- `build_research_report_v2()`: Run full analysis pipeline
- `main.build_research_report_v2()`: CLI orchestration

---

## Analytical Capabilities

### Screening Model

Four fundamental buckets drive the ranking:

1. **Valuation** (Price-to-Sales, P/E)
   - Lower is better; scores derived from percentile ranks
   - Filters for stocks trading below sector medians

2. **Growth** (Revenue Growth, Earnings Growth)
   - Trailing 1-year and forward 1-year EPS growth
   - Forward estimates from consensus analyst research

3. **Quality** (Net Margin, ROE, Debt/Equity)
   - Higher margins and returns rank better
   - Capital efficiency and financial health

4. **Momentum** (1M, 3M, YTD Returns)
   - Trend-following signals
   - Technical confirmation of fundamental setup

**Forward View** (Second Pass):
- Analyst recommendation consensus (Buy/Hold/Sell)
- Price target upside/downside
- Earnings revision trends
- Conviction layers from optional analyst overlays

### DCF Valuation

**Inputs:**
- Base-year free cash flow (from SEC financials)
- Revenue growth rates (3 scenarios: bear, base, bull)
- Terminal growth rate (long-run GDP proxy)
- WACC = Risk-free rate + β × (Market risk premium) – Tax shield
- Net debt and shares outstanding

**Outputs:**
- Intrinsic value per share (3 scenarios)
- Sensitivity matrix (WACC × Terminal Growth Rate)
- Football field chart (DCF range + trading range + peer median)
- Implied upside/downside to current price

**Assumptions:**
- Risk-free rate: 10-year US Treasury yield
- Market risk premium: 5.0% (standard assumption)
- Tax rate: Derived from SEC filings
- Terminal growth: Conservative (long-run GDP growth proxy)

### Risk Analytics

| Metric | Definition | Use |
|--------|-----------|-----|
| **Beta** | Sensitivity to market index | Systematic risk exposure |
| **Volatility (21D, 63D)** | Annualized return standard deviation | Realized price risk |
| **Sharpe Ratio** | (Return – Risk-Free Rate) / Volatility | Risk-adjusted return |
| **Sortino Ratio** | (Return – Risk-Free Rate) / Downside Volatility | Downside risk focus |
| **Max Drawdown** | Peak-to-trough loss | Worst-case scenario |
| **VaR (95%, 1D)** | 95% confidence 1-day loss | Regulatory/compliance metric |
| **CVaR (95%, 1D)** | Expected loss beyond VaR | Tail risk |
| **Correlation** | Spearman rank correlation | Portfolio diversification |

---

## Configuration

### Required Environment Variables

```bash
# SEC EDGAR user identification (best practice for API etiquette)
SEC_USER_AGENT="Your Name your_email@example.com"

# Optional: data cache location (defaults to ./data/cache/)
DATA_CACHE_DIR="/path/to/cache"
```

### Optional Analyst Overlay

Create `data/analyst_views.csv` to add discretionary inputs:

```csv
ticker,stance,conviction,thesis,catalyst,risk,client_angle,management_access_note
NVDA,BUY,HIGH,"AI chip cycle expansion, data center TAM growth","GTC earnings beat, CUDA lock-in","Geopolitical export controls, AMD competition","Semis exposure, structural AI play","CFO confirms strong enterprise demand"
GOOGL,BUY,MEDIUM,"Search resilience, YouTube growth","AI Overviews adoption, Cloud margin inflection","Apple/OpenAI partnership risk, regulatory","Advertising diversification, AI opportunity","CEO commentary on AI ROI positive"
```

Supported columns:
- `ticker`: Stock symbol (required)
- `stance`: BUY / HOLD / SELL
- `conviction`: HIGH / MEDIUM / LOW
- `thesis`: 1–2 sentence investment narrative
- `catalyst`: Near-term events (earnings, product, macro)
- `risk`: Key downside scenarios
- `client_angle`: Why this matters to your specific portfolio/client
- `management_access_note`: Insights from management calls or IR meetings

---

## Running the Pipeline

### Fetch Latest Data

```bash
python main_v2.py fetch-all --as-of 2026-03-27
```

Downloads and caches:
- SEC company facts (fundamentals) for all tickers
- 5 years of daily price history from Yahoo Finance
- ECB rates and FX
- US macro snapshot (yields, VIX, DXY, commodities, sentiment)

### Build Research Report (Full Pipeline)

```bash
python main_v2.py build-report --as-of 2026-03-27
```

Executes:
1. **Fetch** latest data (if not cached)
2. **Screen** stocks across 4 fundamental factors
3. **Value** top candidates using DCF and peer comps
4. **Risk** analyze portfolio risk metrics
5. **Render** full HTML note with embedded PNG charts
6. **Export** as PDF and Markdown

### Build All (Single Command)

```bash
python main_v2.py build-all --as-of 2026-03-27
```

Shortcut for fetch + build-report combined.

### Chart Generation (Windows/Anaconda Note)

Charts require matplotlib/numpy rendering, which has a known DLL conflict with Git Bash on Windows.

**To generate PNG charts, run from:**
- **Anaconda Prompt** (recommended)
- **PowerShell with conda activated**
- **Jupyter notebook**

```bash
# Anaconda Prompt
conda activate prime_quant
python main_v2.py build-all --as-of 2026-03-27
```

Charts will generate correctly from these environments.

---

## Output Files

Generated files are timestamped and stored in `outputs/`:

| File | Format | Contents |
|------|--------|----------|
| `research_note_YYYY-MM-DD.html` | HTML | Full 12-section research note with embedded charts |
| `research_note_YYYY-MM-DD.pdf` | PDF | Printable version of HTML note |
| `daily_note_YYYY-MM-DD.md` | Markdown | Summary note (top picks, macro, key changes) |
| `charts/*.png` | PNG (150 DPI) | Individual chart files (DCF sensitivity, football field, etc.) |

### Sample Outputs

Example research note for March 27, 2026:
- **NVDA**: DCF base $223.56 (5% upside), Sharpe 1.45, Consensus Buy with $200 PT (–5% downside)
- **GOOGL**: DCF base $188.15 (12% upside), Consensus Hold, Cloud margin inflection catalyst
- **MSFT**: Valuation neutral, Quality leader, Momentum positive

---

## Customization

### Modify Stock Watchlist

Edit `trg_workbench/pipeline_v2.py` and update the ticker list:

```python
WATCHLIST = [
    'NVDA', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META',
    # Add your tickers here
]
```

### Adjust Screening Weights

In `trg_workbench/analytics/screening.py`:

```python
WEIGHTS = {
    'valuation': 0.30,   # Price-to-Sales, P/E
    'growth': 0.25,      # Revenue and EPS growth
    'quality': 0.25,     # Margins, ROE, leverage
    'momentum': 0.20,    # Price momentum
}
```

### Customize HTML Template

The 12-section template is in `trg_workbench/reporting/templates/research_note.html.j2`.

Modify colors, sections, chart placement, and narrative using Jinja2 syntax.

### Adjust DCF Assumptions

In `trg_workbench/analytics/valuation.py`:

```python
# Risk-free rate (usually 10Y Treasury)
rfr = 0.042

# Market risk premium
market_risk_premium = 0.05

# Terminal growth rate
terminal_growth_rate = 0.025

# Tax rate (can override per company)
tax_rate = 0.21
```

---

## Testing

Run the test suite:

```bash
pytest
```

Tests cover:
- SEC XBRL parsing and derived metrics
- ECB data normalization
- Stock screening and ranking logic
- Template rendering
- Risk analytics (VaR, correlation, etc.)
- Chart generation

---

## Project Motivation

This project was built to demonstrate:

1. **Production-grade research automation**: Real-world complexity (multi-source data, validation, error handling, edge cases)
2. **Sell-side analyst workflow**: Mirrors institutional research workflows (GS TRG, JPM, MS)
3. **Professional output quality**: Institutional-grade HTML, PDF, and Markdown for client distribution
4. **Transparency**: All data sources and assumptions are documented; no synthetic data
5. **Scalability**: Handles 50+ stock watchlists with full analytical depth (screening, valuation, risk, charts)
6. **Open-source pragmatism**: Uses public data and open-source libraries; caveats and limitations are called out clearly

This is a portfolio piece for roles in equity research, portfolio management, and quantitative research.

---

## Roadmap

- [ ] Real-time price streaming (WebSocket)
- [ ] Options analytics (implied volatility, greeks)
- [ ] Sector rotation dashboard
- [ ] Institutional-grade data sources (Bloomberg API integration)
- [ ] Multi-asset class support (bonds, commodities, crypto)
- [ ] LLM-powered narrative generation
- [ ] Interactive Streamlit app for research collaboration

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes with clear messages
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

**In summary**: You are free to use, modify, and distribute this software for any purpose (commercial or personal), provided you retain the license notice and disclaimer.

---

## Support & Contact

- **Issues & Feature Requests**: Open an issue on GitHub
- **Questions**: Check existing issues or discussions
- **Data source questions**: See [Data Sources](#data-sources) section above

---

## Acknowledgments

- Data sources: SEC EDGAR, Yahoo Finance, ECB SDMX API, yfinance Python library
- Inspiration: Goldman Sachs Tactical Research Group, JPMorgan Equity Research, Morgan Stanley Research
- Charts: matplotlib, seaborn
- PDF rendering: WeasyPrint
- Templating: Jinja2

---

**Last Updated**: March 27, 2026

*For live example outputs, see `outputs/research_note_2026-03-27.html`*
