import json

import pandas as pd

from export_dashboard_data import sector_context, ticker_block
from trg_workbench.pipeline_v2 import value_ticker


def test_ticker_block_has_real_dcf_and_strict_json():
    security_master = pd.DataFrame([{"ticker": "AAA"}])
    fundamentals = pd.DataFrame(
        [{"ticker": "AAA", "net_income": 1e9, "revenue_growth": 0.05, "shares_outstanding": 1e8}]
    )
    px = pd.Series([100.0, 101.0], index=pd.date_range("2026-09-21", periods=2))
    row = pd.Series({
        "ticker": "AAA", "long_name": "Triple A", "sector": "Tech", "market_cap": 1.01e10,
        "target_mean": 120.0, "target_upside": 0.19, "research_score": 0.7,
        "valuation_score": float("nan"), "forward_eps_growth": 0.08,
    })

    val = value_ticker("AAA", security_master, fundamentals, px.to_frame("AAA"))
    block = ticker_block(row, px, val, risk=None, commentary=None)

    assert block["dcf"]["base"] > 0
    assert -90 < block["reverse_dcf"]["implied_growth"] < 100
    assert len(block["reverse_dcf"]["sensitivity"]) == 20
    assert block["dcf"]["wacc"] in {s["wacc"] for s in block["reverse_dcf"]["sensitivity"]}  # grid centered on own WACC
    assert block["factors"]["valuation"] is None  # NaN becomes null, not a fake number
    assert block["rating"] == "BUY"
    json.dumps(block, allow_nan=False)  # raises if any NaN/inf leaks into the JSON


def test_value_ticker_skips_banks():
    sm = pd.DataFrame([{"ticker": "BNK", "industry": "Banks - Diversified",
                        "net_income_to_common": 1e9, "shares_outstanding": 1e8}])
    fundamentals = pd.DataFrame([{"ticker": "BNK", "net_income": 1e9, "shares_outstanding": 1e8}])
    assert value_ticker("BNK", sm, fundamentals, pd.DataFrame({"BNK": [10.0, 11.0]})) is None


def test_sector_context_compares_with_peer_medians():
    eq = {"instrument_group": "us_equity", "sector": "Technology"}
    sm = pd.DataFrame([
        {**eq, "ticker": "AAA", "forward_pe": 30.0, "profit_margins": 0.5, "revenue_growth_next_year": 0.2},
        {**eq, "ticker": "BBB", "forward_pe": 20.0, "profit_margins": 0.3, "revenue_growth_next_year": 0.1},
        {**eq, "ticker": "CCC", "forward_pe": 40.0, "profit_margins": float("nan"), "revenue_growth_next_year": 0.3},
        {"ticker": "XLK", "instrument_group": "sector_proxy", "sector": "Technology", "forward_pe": 99.0},
        {"ticker": "ZZZ", "instrument_group": "us_equity", "sector": "Basic Materials", "forward_pe": 10.0},
    ])
    ctx = sector_context(sm, "AAA")
    assert ctx["etf"] == "XLK" and ctx["peers"] == 2      # self and the ETF row are not peers
    assert ctx["fwd_pe"] == 30.0 and ctx["fwd_pe_median"] == 30.0
    assert ctx["margin_median"] == 30.0                    # NaN peer skipped, shown in pct
    lonely = sector_context(sm, "ZZZ")
    assert lonely["etf"] is None and lonely["fwd_pe_median"] is None  # no ETF fetched, no peers: n/a
