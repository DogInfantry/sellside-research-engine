from datetime import date

import pandas as pd

from trg_workbench.analytics.screening import build_research_dataset, build_stock_callouts, build_price_snapshot


def _price_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=70)
    rows = []
    for ticker, base, slope in [
        ("AAA", 100, 1.2),
        ("BBB", 100, 0.4),
        ("CCC", 100, -0.2),
    ]:
        for index, current_date in enumerate(dates):
            rows.append(
                {
                    "date": current_date,
                    "ticker": ticker,
                    "close": base + (index * slope),
                    "volume": 1_000_000 + index,
                }
            )
    return pd.DataFrame(rows)


def test_build_price_snapshot_calculates_trailing_returns():
    snapshot = build_price_snapshot(_price_frame(), date(2026, 4, 30))

    assert set(snapshot["ticker"]) == {"AAA", "BBB", "CCC"}
    aaa = snapshot.loc[snapshot["ticker"] == "AAA"].iloc[0]
    assert aaa["ret_1w"] > 0
    assert aaa["ret_3m"] > 0


def test_build_research_dataset_ranks_names_and_creates_callouts():
    fundamentals = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "company_name": "Alpha Co",
                "revenue": 1200,
                "previous_revenue": 1000,
                "revenue_growth": 0.20,
                "net_income": 220,
                "equity": 900,
                "shares_outstanding": 10,
                "net_margin": 0.183,
                "roe": 0.244,
            },
            {
                "ticker": "BBB",
                "company_name": "Beta Co",
                "revenue": 1100,
                "previous_revenue": 1050,
                "revenue_growth": 0.05,
                "net_income": 120,
                "equity": 850,
                "shares_outstanding": 10,
                "net_margin": 0.109,
                "roe": 0.141,
            },
            {
                "ticker": "CCC",
                "company_name": "Gamma Co",
                "revenue": 1000,
                "previous_revenue": 980,
                "revenue_growth": 0.02,
                "net_income": 80,
                "equity": 900,
                "shares_outstanding": 10,
                "net_margin": 0.080,
                "roe": 0.089,
            },
        ]
    )
    metadata = pd.DataFrame(
        [
            {"ticker": "AAA", "instrument_group": "us_equity", "sector": "Technology", "long_name": "Alpha Co"},
            {"ticker": "BBB", "instrument_group": "us_equity", "sector": "Financials", "long_name": "Beta Co"},
            {"ticker": "CCC", "instrument_group": "us_equity", "sector": "Industrials", "long_name": "Gamma Co"},
        ]
    )

    research = build_research_dataset(fundamentals, _price_frame(), metadata, date(2026, 4, 30))

    assert research.iloc[0]["ticker"] == "AAA"
    assert research["composite_score"].notna().all()
    assert len(build_stock_callouts(research, limit=2)) == 2

