# Real-Data TRG Research Workbench

This repo is a sell-side style research pipeline built to mirror the shape of a Tactical Research Group analyst workflow in Goldman Sachs Global Investment Research.

It pulls only real data from live sources, normalizes the data into a local research-ready layer, scores a US single-stock watchlist, overlays Europe macro and index context, and publishes three outputs:

- A daily tactical note
- A weekly research wrap
- A management KPI report based on real pipeline activity

It also supports an optional analyst overlay file for discretionary stance, conviction, thesis, catalyst, risk, and client-angle notes.

## Why this fits the role

The project maps directly to the job description:

- `Research merchandising`: daily and weekly publishable notes rendered from data, templates, and deterministic commentary rules
- `Bottom-up equity research`: US stock screening with valuation, growth, profitability, and momentum metrics derived from SEC fundamentals plus market prices
- `Forward-looking earnings work`: Yahoo Finance earnings estimates, recommendation trends, price targets, and public company calendar data
- `Analyst judgment`: optional discretionary overlays for stance, conviction, thesis, catalysts, risks, and client-facing angles
- `Global divisional projects / metrics`: a KPI report based on actual data fetches, report generation cadence, and source coverage

## Data sources

- `SEC company facts / filings`: authoritative US fundamentals and shares outstanding
- `ECB data API`: Europe macro and FX context
- `yfinance`: end-of-day market prices, sector proxy ETFs, and Europe index prices

Notes:

- No synthetic or hand-made investment datasets are used in the pipeline.
- `yfinance` is convenient for research workflows, but it is not an official exchange feed. The README calls that out explicitly because interviewers often care about source quality and caveats.
- For best SEC etiquette, set `SEC_USER_AGENT` with your contact details before running the fetch step.
- The pipeline uses `SEC` as the primary fundamentals source and falls back to Yahoo fundamental fields only when SEC blocks requests in restricted environments. The fallback still uses real market data; it just trades off source quality for portability.
- Proprietary datasets like Bloomberg, FactSet, and Datastream are not replicable for free. This repo uses public/free proxies instead of pretending to have premium feeds.
- True management access is also not replicable for free. The nearest honest substitutes here are public company calendar data and optional analyst-authored management/IR notes in the overlay file.

## Repo structure

```text
main.py
trg_workbench/
  sources/        # SEC, ECB, Yahoo Finance adapters
  analytics/      # screening, market summaries, KPI prep
  reporting/      # Jinja templates and chart rendering
  pipeline.py     # fetch/build orchestration
tests/
outputs/          # generated notes, KPI report, and charts
data/analyst_views_template.csv  # optional discretionary analyst overlay template
```

## Setup

Install the dependencies:

```bash
pip install -r requirements.txt
```

If `python` is not on your PATH in this environment, use the explicit interpreter:

```powershell
& 'C:\Users\Anklesh\anaconda3\python.exe' -m pip install -r requirements.txt
```

Set a SEC user agent before live fetches:

```powershell
$env:SEC_USER_AGENT = "Your Name your_email@example.com"
```

## Commands

Fetch and normalize the latest data cut:

```bash
python main.py fetch-data --as-of 2026-03-26
```

Build the reports individually:

```bash
python main.py build-daily --date 2026-03-26
python main.py build-weekly --week-ending 2026-03-26
python main.py build-kpis --month 2026-03
```

Run the full pipeline:

```bash
python main.py build-all --as-of 2026-03-26
```

## Output files

- `outputs/daily_note_YYYY-MM-DD.md`
- `outputs/weekly_wrap_YYYY-MM-DD.md`
- `outputs/kpi_report_YYYY-MM.html`
- `outputs/charts/*.png`

## Optional analyst overlay

If you want discretionary calls in the published notes, create `data/analyst_views.csv` using the header layout in `data/analyst_views_template.csv`.

Supported columns:

- `ticker`
- `stance`
- `conviction`
- `thesis`
- `catalyst`
- `risk`
- `client_angle`
- `management_access_note`

## Screening model

The composite screen blends four buckets:

- `Valuation`: lower price-to-sales and lower P/E rank better
- `Growth`: higher trailing revenue growth ranks better
- `Quality`: higher net margin and ROE rank better
- `Momentum`: stronger one-month and three-month returns rank better

The final ranking then layers on:

- `Forward score`: next-year EPS growth, target-price upside, recommendation breadth, and recommendation trend
- `Discretionary overlay`: optional stance and conviction inputs if `data/analyst_views.csv` is present

This keeps the system transparent while making the output feel more like a research workflow than a pure trailing-factor table.

## Testing

Run the test suite with:

```bash
pytest
```

The tests cover:

- SEC fact parsing and derived metrics
- ECB response normalization
- Screening and ranking logic
- Template rendering
- KPI aggregation from pipeline logs

## Git / portfolio packaging

Suggested flow after implementation:

```bash
git branch -M main
git add .
git commit -m "Build real-data TRG research workbench"
git remote add origin <your-github-repo-url>
git push -u origin main
```

Because `gh` is not installed in this environment, create the GitHub repo in the browser first and then add the remote URL locally.
