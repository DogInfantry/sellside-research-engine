# v1.2.0 — CLI Refactor, Quiet Mode, PDF Fallback & Session Output Infrastructure

**Released:** 12 April 2026  
**Previous:** [v1.1.0](https://github.com/DogInfantry/sellside-research-engine/releases/tag/v1.1.0)

---

## ✨ What's New

### Engine Changes
- **CLI refactor & quiet-aware progress bars** — `--quiet` flag now suppresses all tqdm output for clean CI/CD pipelines and scheduled runs (`@joepaulvilsan`, PR merged Apr 12)
- **PDF rendering fallback** — WeasyPrint failures no longer crash the pipeline; graceful fallback with warning logged to `outputs/` (`@joepaulvilsan`)
- **Automated chart integration** — charts are now auto-discovered and embedded into the HTML report without manual path configuration (`@joepaulvilsan`)
- **Universal `--quiet` support** — propagated across `pipeline_v2.py`, `reporting/charts.py`, and the reporting layer
- **Test suite aligned** — reporting tests updated to match new `pipeline_v2` context schema

### Session Output Infrastructure
- **Session folders** — each `build-all` run now drops outputs into `outputs/session_YYYY-MM-DD/` instead of the flat `outputs/` root, enabling clean per-session versioning
- **`research_note_YYYY-MM-DD.md`** — Markdown version of the institutional research note added as a new output artifact (renders as PDF in GitHub / Perplexity; Git-friendly and diffable)
- **Session README** — auto-generated `README.md` per session with macro regime summary, top picks, key changes vs previous run

### Session 2026-04-12 Output
- **Watchlist:** NVDA, MSFT, AAPL, XOM, JNJ
- **Macro Regime:** Risk-On / Yield Curve Steepening (VIX 18.4, 10Y–2Y −39bps)
- **Top Picks:** NVDA BUY $941 (+7.5%) · MSFT BUY $451 (+9.4%)
- **Files:** [`outputs/session_2026-04-12/`](https://github.com/DogInfantry/sellside-research-engine/tree/main/outputs/session_2026-04-12)

---

## 🔧 Fixes
- `outputs/` re-added to tracked paths for session folders (previously fully gitignored in v1.1.0 — now `outputs/session_*/` is tracked, raw HTML excluded)
- Orphaned chart generation loop patched to pass context correctly

---

## 📊 Pipeline Output Summary (v1.2.0)

| Artifact | Format | Description |
|---|---|---|
| `research_note_YYYY-MM-DD.html` | HTML | Full 12-section GS-style note, all charts base64-embedded |
| `research_note_YYYY-MM-DD.pdf` | PDF | WeasyPrint render (fallback: skip with warning) |
| `research_note_YYYY-MM-DD.md` | Markdown | **New in v1.2.0** — Diffable, GitHub-renderable research note |
| `daily_note_YYYY-MM-DD.md` | Markdown | Compact daily brief for Obsidian / Notion / Git workflows |
| `session_YYYY-MM-DD/README.md` | Markdown | **New in v1.2.0** — Session summary + diff vs previous run |

---

## 🚧 Still Pending (Roadmap)

- **Issue #9** — LLM earnings transcript RAG layer (LangChain + Whisper)
- **Issue #6** — Reverse DCF module
- **Issue #10** — Interactive Plotly charts replacing static PNGs
- **Issue #7** — Excel DCF export with live formula links

---

## Contributors

- [@DogInfantry](https://github.com/DogInfantry) — session infrastructure, release management
- [@joepaulvilsan](https://github.com/joepaulvilsan) — CLI refactor, quiet mode, PDF fallback, chart integration
- [@kenimoraj](https://github.com/kenimoraj) — progress bars (v1.1.0, carried forward)
- [@CrestXcode](https://github.com/CrestXcode) — `--dry-run` flag (v1.1.0, carried forward)

---

*TRG Research Workbench · github.com/DogInfantry/sellside-research-engine*
