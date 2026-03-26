import pandas as pd

from trg_workbench.reporting.renderers import render_template


def test_daily_template_renders_key_sections():
    content = render_template(
        "daily_note.md.j2",
        {
            "report_date": "2026-03-26",
            "data_as_of": "2026-03-26",
            "macro_summary": [
                {
                    "display_name": "USD per EUR",
                    "category": "fx",
                    "latest_value": 1.08,
                    "one_week_change": 0.01,
                    "last_updated": pd.Timestamp("2026-03-26"),
                }
            ],
            "sector_summary": [
                {
                    "display_name": "Technology",
                    "ticker": "XLK",
                    "ret_1d": 0.01,
                    "ret_1w": 0.03,
                    "ret_1m": 0.08,
                }
            ],
            "europe_summary": [
                {
                    "display_name": "Euro Stoxx 50",
                    "ticker": "^STOXX50E",
                    "ret_1d": 0.01,
                    "ret_1w": 0.02,
                    "ret_1m": 0.05,
                }
            ],
            "top_candidates": [
                {
                    "screen_rank": 1,
                    "ticker": "GS",
                    "company_name": "Goldman Sachs Group, Inc.",
                    "sector": "Financials",
                    "forward_eps_growth": 0.12,
                    "target_upside": 0.18,
                    "analyst_buy_ratio": 0.85,
                    "research_score": 0.91,
                }
            ],
            "sector_narratives": ["Technology and Financials have improving forward setups."],
            "catalyst_calendar": [],
            "analyst_overlays": [],
            "takeaways": ["Financials are leading this week."],
        },
    )

    assert "# Daily Tactical Note" in content
    assert "US Sector Tape" in content
    assert "Goldman Sachs Group, Inc." in content
