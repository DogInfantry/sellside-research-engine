# Release Notes — v1.3.0

**Release Date:** April 12, 2026  
**Tag:** `v1.3.0`  
**Branch:** `main`

---

## Overview

v1.3.0 is a significant capability expansion, shipping three major features: **Reverse DCF analytics**, a **Management Commentary transcript MVP**, and a set of **CLI quality-of-life improvements** contributed by the community. The pipeline now covers the full analyst loop — from XBRL fundamentals and earnings transcript extraction through to implied growth rate diagnostics and institutional research note rendering.

---

## New Features

### 🔄 Reverse DCF Analytics (`valuation.py`)
- Back-solves the implied FCF growth rate priced into the current market price given WACC and terminal growth assumptions
- Outputs implied growth rate + delta vs. analyst consensus to flag stretched or discounted valuations
- Sensitivity table: implied growth across a matrix of WACC × terminal growth rate combos
- Integrated into the existing DCF football field chart for a unified valuation view
- Merged via [PR #17](https://github.com/DogInfantry/sellside-research-engine/pull/17)

### 🎙️ Management Commentary Transcript MVP (`management_commentary.py`)
- Ingests earnings call transcripts (plain text or structured format)
- LLM-driven extraction of: guidance tone (positive/neutral/cautious), key revenue and margin themes, forward-looking statements with source tagging, and risk flags (supply chain, macro sensitivity, competitive threats)
- Output integrates into the research note narrative section and is also exported as a standalone JSON artifact
- Supports pluggable transcript sources — paste raw text or point to a file path
- Merged via [PR #18](https://github.com/DogInfantry/sellside-research-engine/pull/18)

### ⚙️ CLI Enhancements
- **`--dry-run` flag** ([PR #13](https://github.com/DogInfantry/sellside-research-engine/pull/13) by [@CrestXcode](https://github.com/CrestXcode)) — validates all inputs and data source connectivity without making live API calls; safe for CI gating
- **`tqdm` progress bars** ([PR #12](https://github.com/DogInfantry/sellside-research-engine/pull/12) by [@kenimoraj](https://github.com/kenimoraj)) — added to all fetch loops in `pipeline_v2.py` and chart generation in `reporting/charts.py`
- **`--quiet` mode** and **PDF fallback rendering** contributed by [@joepaulvilsan](https://github.com/joepaulvilsan) — suppresses verbose output for automated pipelines; gracefully handles WeasyPrint unavailability with fallback rendering path

---

## Documentation Updates

- README updated to reflect v1.3.0 features: reverse DCF, management commentary, CLI flags, updated architecture tree, and roadmap status
- Roadmap items for reverse DCF, transcript RAG pipeline, `--dry-run`, and progress bars marked as shipped (`✅`)
- Analyst views schema documentation (shipped in v1.2.0) retained and cross-referenced
- Inline changelog section added to README for quick release history

---

## Bug Fixes & Maintenance

- Analyst views schema fully documented ([PR #16](https://github.com/DogInfantry/sellside-research-engine/pull/16)) — previously undocumented CSV fields now have type, valid values, and descriptions
- Session output pipeline stable: research note, daily brief, and session README generated correctly for April 12 session
- `outputs/` directory correctly excluded from version control via `.gitignore`

---

## Contributors

Thank you to everyone who shipped features in this release:

| Contributor | Feature |
|---|---|
| [@CrestXcode](https://github.com/CrestXcode) | `--dry-run` CLI flag |
| [@kenimoraj](https://github.com/kenimoraj) | `tqdm` progress bars |
| [@joepaulvilsan](https://github.com/joepaulvilsan) | `--quiet` mode, PDF fallback, chart integration |

---

## Upgrading from v1.2.0

No breaking changes. Run `pip install -r requirements.txt` to pick up any new dependencies added by the management commentary and transcript modules.

```bash
git pull origin main
pip install -r requirements.txt
```

---

## What's Next (v1.4.0 Candidates)

- Piotroski F-Score and Altman Z-Score in the screening model
- FRED API connector (CPI, PCE, credit spreads, yield curve)
- GitHub Actions CI — automated pytest on every PR
- Interactive HTML report with Plotly charts replacing static PNGs
- LBO model stub — entry/exit IRR analysis

See the [Issues tab](https://github.com/DogInfantry/sellside-research-engine/issues) for full specs and contribution opportunities.
