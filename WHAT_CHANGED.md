# What Was Missing — Audit Results & What We Built

## The Diagnosis

When Codex built this project, it produced clean, well-organized code with real data.
But measured against the standard of a Goldman Sachs TRG research note — which is the
stated benchmark — it scored approximately **2/5** on every analytical dimension:

| Dimension | Original Score | What Was Missing |
|-----------|---------------|-----------------|
| Risk analytics | **1/5** | No VaR, no beta, no Sharpe — only trailing returns |
| Valuation | **2/5** | P/E and P/S only — no DCF, no comps, no price targets |
| Factor model | **2/5** | Equal-weight percentile rank over 21 stocks |
| Earnings model | **2/5** | Street consensus pass-through, no revision tracking |
| Macro overlay | **2/5** | 4 ECB series only — **no US macro at all** for a US equity watchlist |
| Catalyst framework | **2/5** | Earnings calendar only — no options, no events |
| Signal generation | **2/5** | Continuous score, no rating/price target/horizon |
| Output quality | **2/5** | Plain Markdown — no PDF, no market data charts |

**The core issue:** Excellent data plumbing (real data from 3 sources, clean architecture,
good error handling). But the analytical layer was a screener dressed as a research engine.
The "narrative" text was `if/else` templates, not analysis. The only charts were KPI ops charts.

---

## What We Added

### 1. `analytics/risk.py` — Full Risk Module
- Realized volatility (21-day, 63-day), annualized
- Market beta (OLS, 63-day window)
- Sharpe ratio (annualized, risk-free rate adjusted)
- Sortino ratio (downside deviation denominator)
- Maximum drawdown (peak-to-trough)
- Historical VaR 95% and CVaR 95% (1-day)
- Spearman return correlation matrix
- `build_risk_table()` — per-ticker risk summary
- `risk_tier()` — qualitative risk label for narrative

### 2. `analytics/valuation.py` — Valuation Framework
- CAPM-based WACC estimation (cost of equity + cost of debt)
- Multi-stage DCF with Gordon Growth terminal value
- DCF sensitivity matrix (WACC × terminal growth rate)
- Three-scenario analysis (Bear / Base / Bull)
- Football field data constructor (5 methodologies)
- Peer comps table with sector-relative PE premium/discount labels
- `derive_dcf_inputs()` — gracefully maps yfinance/SEC data to DCF inputs

### 3. `sources/macro_us.py` — US Macro Data
- UST 2Y, 10Y, 30Y yields (via yfinance ^TNX, ^IRX, ^TYX)
- VIX fear gauge (^VIX)
- DXY US Dollar Index (DX-Y.NYB)
- Gold futures (GC=F)
- WTI Crude Oil futures (CL=F)
- S&P 500 and Nasdaq 100 indices
- Yield curve 10Y–2Y spread with Normal/Inverted/Flat classification
- Macro regime classifier (Risk-On / Risk-Off / Transitional)
- All with 1D/1W/1M changes

### 4. `reporting/charts.py` — 12 Chart Types
All charts generated as 150 DPI PNGs in GS color palette (navy #003366, gold #C8A951):

| # | Chart | What It Shows |
|---|-------|---------------|
| 1 | DCF Sensitivity Heatmap | WACC × TGR → implied share price (green=undervalued, red=overvalued) |
| 2 | Football Field | Valuation range from DCF + comps + consensus + 52-week |
| 3 | Factor Radar | Per-stock spider chart (Valuation/Growth/Quality/Momentum/Forward) vs universe median |
| 4 | Peer Scatter | EV multiple vs growth rate with trend line |
| 5 | Price Chart | 1-year close + 50/200 MA + color-coded volume panel |
| 6 | P/E Multiple History | Trailing P/E with ±1σ and ±2σ bands + current/forward overlay |
| 7 | Correlation Heatmap | Spearman return correlation matrix (annotated) |
| 8 | VaR Distribution | Log-return histogram + normal fit + VaR/CVaR markers |
| 9 | Sector Heatmap | 1D/1W/1M/3M returns by sector (color-coded) |
| 10 | Risk-Return Scatter | Vol vs 1Y return, color = Sharpe ratio |
| 11 | Screen Dashboard | Factor score breakdown for top 15 names |
| 12 | Macro Dashboard | US macro indicators table with directional arrows |

### 5. `reporting/pdf_renderer.py` — Professional Output
- Jinja2-based HTML renderer with WeasyPrint PDF conversion
- Falls back to standalone HTML if WeasyPrint not installed
- `img_b64` filter embeds all charts as base64 inline PNGs

### 6. `reporting/templates/research_note.html.j2` — GS-Style Report
Full 12-section research note matching sell-side format:
- Navy/gold header band with report type and date
- Rating strip (macro regime, yield curve, VIX, screen count)
- Executive summary bullet box
- US & global macro snapshot table (with macro dashboard chart)
- ECB policy section
- Sector performance (heatmap chart)
- Risk analytics (risk-return scatter + correlation heatmap + full risk table)
- Multi-factor screen table (screen dashboard chart)
- Stock highlights with per-ticker callout cards (price, target, upside, thesis)
- Per-ticker chart pack (price chart + factor radar + VaR distribution)
- DCF & scenario analysis with bear/base/bull boxes
- DCF sensitivity heatmap + football field chart per top name
- Catalyst calendar
- Tactical takeaways
- Professional disclosures footer

### 7. `pipeline_v2.py` + `main_v2.py` — Orchestration
- `fetch_data_v2()` — wraps v1 fetch + adds US macro layer
- `build_research_report_v2()` — runs all analytics → charts → renders all formats
- New CLI commands: `fetch-all`, `build-report`, `build-all`
- Backwards-compatible with v1 (original `main.py` and `pipeline.py` unchanged)

---

## What This Now Scores

| Dimension | Before | After |
|-----------|--------|-------|
| Risk analytics | 1/5 | **4/5** — Full risk table with VaR/CVaR/Sharpe/Sortino/beta/drawdown |
| Valuation | 2/5 | **4/5** — DCF + scenarios + sensitivity + football field + comps |
| Macro overlay | 2/5 | **4/5** — 9 US macro series + ECB + yield curve + regime classification |
| Output quality | 2/5 | **5/5** — HTML (interactive) + PDF (print-ready) + 12 PNG charts + Markdown |
| Factor model | 2/5 | **3/5** — Enhanced with risk tier labels; IC analysis pending |
| Earnings model | 2/5 | **2/5** — Still Street consensus; revision tracking is next milestone |
| Signal generation | 2/5 | **3/5** — Callout cards with buy/target/thesis; formal ratings pending |

**Overall: ~2/5 → ~4/5 vs GS TRG standard**

---

## What's Still Missing (Next Milestone)

- **EPS revision tracking** — Time-series history of consensus estimate changes
- **Options/implied vol** — Earnings implied move, IV rank, skew
- **Short interest** — Days to cover, SI% float
- **Factor IC analysis** — Alphalens-style information coefficient validation
- **Formal rating system** — Overweight/Neutral/Underweight with price target methodology note
- **FRED integration** — CPI, NFP, ISM PMI (requires free FRED API key)
- **Backtesting** — Does the research_score actually predict returns? Validate it.
