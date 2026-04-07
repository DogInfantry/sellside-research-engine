# Contributing to Sell-Side Research Engine

Thank you for your interest in contributing! This project welcomes contributions from equity researchers, quants, data engineers, and Python developers.

---

## 📋 Table of Contents

- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Issue Labels](#issue-labels)
- [Code Standards](#code-standards)
- [Good First Issues](#good-first-issues)

---

## Getting Started

1. **Fork** the repository via the GitHub UI
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/sellside-research-engine.git
   cd sellside-research-engine
   ```
3. **Create a virtual environment** and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Set your SEC user agent:
   ```bash
   export SEC_USER_AGENT="Your Name your_email@example.com"
   ```
5. Run the test suite to confirm everything works:
   ```bash
   pytest
   ```

---

## How to Contribute

### 🐛 Reporting Bugs

Open an issue using the **Bug Report** template. Include:
- Python version and OS
- Full stack trace
- Minimal reproducible example (ticker, date, command)

### 💡 Proposing Features

Open an issue using the **Feature Request** template. Describe:
- The problem you're solving (e.g., "CCA currently uses trailing multiples; forward multiples would improve accuracy")
- Your proposed approach
- Any financial / data-sourcing constraints

### 🔧 Submitting Code

See [Pull Request Guidelines](#pull-request-guidelines) below.

---

## Development Setup

```
sellside-research-engine/
├── trg_workbench/
│   ├── sources/        ← Data connectors (SEC, Yahoo, ECB, macro)
│   ├── analytics/      ← Screening, valuation, risk, catalyst
│   └── reporting/      ← Charts, PDF renderer, Jinja2 templates
├── tests/              ← pytest test suite
├── main_v2.py          ← CLI entry point
└── requirements.txt
```

Each module is intentionally self-contained. A contribution to `valuation.py` should not require changes to `sec_client.py`.

---

## Pull Request Guidelines

1. **Branch naming**: `feature/<short-description>`, `fix/<short-description>`, `docs/<short-description>`
2. **Keep PRs focused** — one logical change per PR
3. **Write tests** for any new analytics or data-pipeline logic (under `tests/`)
4. **Run the full test suite** before opening your PR:
   ```bash
   pytest
   ```
5. **Update the README** if you add a new CLI flag, data source, or output format
6. **PR description** should include:
   - What changed and why
   - How to test it manually (ticker + date + command)
   - Any known limitations

---

## Issue Labels

| Label | Meaning |
|-------|---------|
| `good first issue` | Self-contained, well-scoped — ideal for new contributors |
| `help wanted` | We'd love external input on this |
| `bug` | Confirmed defect |
| `enhancement` | New feature or improvement |
| `data-source` | Relates to a specific API integration |
| `analytics` | Screening, valuation, or risk logic |
| `reporting` | HTML/PDF/Markdown output layer |
| `llm` | LLM reasoning / narrative generation |

---

## Code Standards

- **Python 3.10+**, typed where practical (`from __future__ import annotations`)
- **Black** formatting (line length 100)
- **Descriptive variable names** — financial models are read more than written
- No hardcoded tickers, dates, or magic numbers in module-level code (use constants or CLI args)
- External API calls must be rate-limited and respect the service's Terms of Service

---

## Good First Issues

Not sure where to start? Look for issues tagged [`good first issue`](https://github.com/DogInfantry/sellside-research-engine/labels/good%20first%20issue). Suggestions currently on the roadmap that are contributor-friendly:

- Add a new CLI flag to filter by sector in the screener
- Improve the Markdown daily note formatting
- Add unit tests for `catalyst.py`
- Document the `analyst_views.csv` column schema in the README
- Add a `--dry-run` flag that validates inputs without hitting live APIs

---

## Questions?

Open a [Discussion](https://github.com/DogInfantry/sellside-research-engine/discussions) or comment on an existing issue. Financial domain questions (e.g., "what WACC convention should we use?") are welcome.
