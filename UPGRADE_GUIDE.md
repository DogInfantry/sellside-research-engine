# TRG Research Workbench v2 — Integration Guide

## Overview

This upgrade transforms the project from a data pipeline with a Markdown screener
into a full sell-side research engine that produces:
- Professional HTML research notes (GS-style, print-ready)
- PDF reports (via WeasyPrint)
- 12 types of publication-quality PNG charts
- DCF valuation with bear/base/bull scenarios
- Full risk analytics (VaR, CVaR, Sharpe, Sortino, beta, drawdown)
- US macro overlay (Fed, UST yields, VIX, DXY, Gold, WTI)

---

## Step 1: Clone Your Repo

```bash
git clone https://github.com/DogInfantry/sellside-research-engine.git
cd sellside-research-engine
```

---

## Step 2: Copy New Files

Copy these files from the `sellside-upgrade/` folder into your repo:

```
sellside-upgrade/
├── trg_workbench/
│   ├── analytics/
│   │   ├── risk.py                    → trg_workbench/analytics/risk.py
│   │   └── valuation.py               → trg_workbench/analytics/valuation.py
│   ├── sources/
│   │   └── macro_us.py                → trg_workbench/sources/macro_us.py
│   └── reporting/
│       ├── charts.py                  → trg_workbench/reporting/charts.py
│       ├── pdf_renderer.py            → trg_workbench/reporting/pdf_renderer.py
│       └── templates/
│           └── research_note.html.j2  → trg_workbench/reporting/templates/research_note.html.j2
├── pipeline_v2.py                     → trg_workbench/pipeline_v2.py
├── main_v2.py                         → main_v2.py
└── requirements_v2.txt                → (merge into requirements.txt)
```

### Quick copy commands (Windows PowerShell):

```powershell
$SRC = "C:\Users\Anklesh\Documents\sellside-upgrade"
$REPO = "C:\path\to\sellside-research-engine"  # CHANGE THIS

# Analytics
Copy-Item "$SRC\trg_workbench\analytics\risk.py"       "$REPO\trg_workbench\analytics\"
Copy-Item "$SRC\trg_workbench\analytics\valuation.py"  "$REPO\trg_workbench\analytics\"

# Sources
Copy-Item "$SRC\trg_workbench\sources\macro_us.py"     "$REPO\trg_workbench\sources\"

# Reporting
Copy-Item "$SRC\trg_workbench\reporting\charts.py"         "$REPO\trg_workbench\reporting\"
Copy-Item "$SRC\trg_workbench\reporting\pdf_renderer.py"   "$REPO\trg_workbench\reporting\"
Copy-Item "$SRC\trg_workbench\reporting\templates\research_note.html.j2" "$REPO\trg_workbench\reporting\templates\"

# Pipeline & CLI
Copy-Item "$SRC\pipeline_v2.py"  "$REPO\trg_workbench\"
Copy-Item "$SRC\main_v2.py"      "$REPO\"
```

---

## Step 3: Install Dependencies

```bash
pip install scipy numpy seaborn

# For PDF output (optional but recommended):
pip install weasyprint

# WeasyPrint on Windows requires GTK+ runtime first:
# Download from: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
# Install GTK, then: pip install weasyprint
#
# If GTK is too much hassle, skip it — the pipeline auto-falls back to HTML.
# Open the HTML in Chrome → Ctrl+P → "Save as PDF" → print-quality PDF.
```

---

## Step 4: Set Environment Variable

```bash
# Required for SEC EDGAR access
set SEC_USER_AGENT=YourName/1.0 (your@email.com)

# PowerShell:
$env:SEC_USER_AGENT = "YourName/1.0 (your@email.com)"
```

---

## Step 5: Run

```bash
# Option A: Fetch all data + generate all outputs in one command
python main_v2.py build-all --as-of 2026-03-27

# Option B: Separate steps
python main_v2.py fetch-all --as-of 2026-03-27
python main_v2.py build-report --as-of 2026-03-27

# Option C: Specific formats only
python main_v2.py build-report --as-of 2026-03-27 --formats html,markdown
```

---

## Step 6: Find Your Outputs

```
outputs/
├── research_note_2026-03-27.html    ← Open in browser (full report, charts embedded)
├── research_note_2026-03-27.pdf     ← Professional PDF (requires WeasyPrint)
├── daily_note_2026-03-27.md         ← Original Markdown note (unchanged)
└── charts/
    ├── sector_heatmap_2026_03_27.png
    ├── screen_dashboard_2026_03_27.png
    ├── risk_return_2026_03_27.png
    ├── correlation_heatmap_2026_03_27.png
    ├── macro_dashboard_2026_03_27.png
    ├── price_NVDA_2026_03_27.png
    ├── radar_NVDA_2026_03_27.png
    ├── var_NVDA_2026_03_27.png
    ├── dcf_sensitivity_NVDA_2026_03_27.png
    ├── football_NVDA_2026_03_27.png
    └── ... (per top-3 tickers)
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: scipy` | `pip install scipy` |
| `ModuleNotFoundError: weasyprint` | Skip PDF — HTML output still works. Or install GTK first. |
| `No price data available` | Run `python main_v2.py fetch-all --as-of DATE` first |
| `DCF inputs base_fcf = 0` | Company has no net income data — valuation skipped for that ticker |
| Charts not appearing in HTML | PNG paths are embedded as base64 — check `outputs/charts/` exists and has write permission |
| yfinance rate limit | Add `time.sleep(1)` in `sources/market.py` between ticker fetches |

---

## Architecture: What's New vs Original

```
ORIGINAL (v1)                          NEW (v2)
─────────────────────────────────────────────────────────────
sources/market.py (yfinance)           + sources/macro_us.py (US macro)
sources/sec.py    (SEC EDGAR)            (VIX, DXY, UST yields, Gold, WTI)
sources/ecb.py    (ECB rates)
                                       + analytics/risk.py
analytics/screening.py                   (VaR, CVaR, beta, Sharpe, Sortino,
analytics/summaries.py                    max drawdown, correlation matrix)
analytics/kpis.py
                                       + analytics/valuation.py
                                          (DCF, sensitivity, football field,
                                           bear/base/bull scenarios, comps)

reporting/renderers.py (3 KPI charts)  + reporting/charts.py (12 chart types)
reporting/templates/daily_note.md.j2   + reporting/pdf_renderer.py
reporting/templates/weekly_wrap.md.j2  + reporting/templates/research_note.html.j2
reporting/templates/kpi_report.html.j2

pipeline.py                            + pipeline_v2.py (orchestrates everything)
main.py                                + main_v2.py (new CLI commands)
```
