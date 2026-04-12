from trg_workbench.reporting.pdf_renderer import render_html_report
from trg_workbench.reporting.renderers import render_template


def test_daily_template_renders_key_sections():
    content = render_template(
        "daily_note.md.j2",
        {
            "report_title": "Daily Tactical Note",  # Matches context['report_title']
            "as_of_date": "2026-03-26",  # Matches context['as_of_date']
            "us_macro_rows": [  # Matches us_macro_rows in v2
                {
                    "label": "USD per EUR",
                    "value_fmt": "1.08",
                    "chg_1w": 0.01,
                }
            ],
            "sector_rows": [  # Matches sector_rows in v2
                {
                    "sector_name": "Technology",
                    "ticker": "XLK",
                    "ret_1w": 0.03,
                }
            ],
            "screen_rows": [  # CRITICAL FIX: Changed from top_candidates
                {
                    "ticker": "GS",
                    "company_name": "Goldman Sachs Group, Inc.",
                    "research_score": 0.91,
                    "target_upside": 0.18,
                }
            ],
            "catalyst_rows": [],
            "dcf_results": [
                {
                    "ticker": "GS",
                    "reverse_dcf": {
                        "implied_growth_rate": 0.12,
                        "wacc": 0.09,
                        "terminal_growth": 0.025,
                    },
                }
            ],
            "management_commentary": [
                {
                    "ticker": "GS",
                    "tone_score": 0.72,
                    "guidance_summary": "Management raised guidance.",
                    "key_risks": ["FX headwinds remain."],
                    "catalyst_flags": ["New product launch in Q3."],
                }
            ],
            "tactical_takeaways": ["Financials are leading this week."],
        },
    )

    assert "# Daily Tactical Note" in content
    assert "US Sector Tape" in content
    assert "Goldman Sachs Group, Inc." in content
    assert "GS: market implies 12.0% FCF CAGR" in content
    assert "Management Commentary" in content
    assert "Management raised guidance." in content


def test_html_template_renders_reverse_dcf_section():
    content = render_html_report(
        {
            "report_title": "Research Note",
            "as_of_date": "2026-03-26",
            "charts": {},
            "dcf_results": [
                {
                    "ticker": "GS",
                    "current_price": 100.0,
                    "reverse_dcf": {
                        "implied_growth_rate": 0.12,
                        "implied_ev": 1_250_000_000,
                        "projection_years": 10,
                        "terminal_growth": 0.025,
                        "wacc": 0.09,
                        "sensitivity": {
                            "wacc_down_100bps": {"implied_growth_rate": 0.10},
                            "wacc_up_100bps": {"implied_growth_rate": 0.14},
                        },
                    },
                }
            ],
            "management_commentary": [
                {
                    "ticker": "GS",
                    "tone_score": 0.72,
                    "analyst_qa_tone": "constructive",
                    "source": "heuristic_transcript_parser",
                    "guidance_summary": "Management raised guidance.",
                    "key_risks": ["FX headwinds remain."],
                    "catalyst_flags": ["New product launch in Q3."],
                }
            ],
        }
    )

    assert "Market-Implied FCF CAGR" in content
    assert "12.0%" in content
    assert "Management Commentary" in content
