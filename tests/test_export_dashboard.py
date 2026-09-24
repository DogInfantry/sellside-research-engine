import json

import numpy as np
import pandas as pd

from export_dashboard_data import pe_growth_fit, sector_block, sector_context, ticker_block
from trg_workbench.analytics.valuation import build_comps_table
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
    comps = build_comps_table(sm)
    ctx = sector_context(comps, "AAA")
    assert ctx["etf"] == "XLK" and ctx["peers"] == 2      # self and the ETF row are not peers
    assert ctx["fwd_pe"] == 30.0 and ctx["fwd_pe_median"] == 30.0
    assert ctx["margin_median"] == 30.0                    # NaN peer skipped, shown in pct
    assert ctx["ev_ebitda"] is None and ctx["ev_ebitda_median"] is None  # no EV data: n/a
    fin = {"instrument_group": "us_equity", "sector": "Financial Services", "forward_pe": 12.0}
    banks = build_comps_table(pd.DataFrame([
        {**fin, "ticker": "AM", "industry": "Asset Management", "enterprise_value": 150.0, "ebitda": 10.0},
        *[{**fin, "ticker": t, "industry": "Banks - Diversified"} for t in ["B1", "B2", "B3"]],
    ]))
    bank = sector_context(banks, "B1")
    assert bank["ev_ebitda_median"] is None  # one asset manager is not the median of three peers
    assert bank["fwd_pe_median"] == 12.0
    lonely = sector_context(comps, "ZZZ")
    assert lonely["etf"] is None and lonely["fwd_pe_median"] is None  # no ETF fetched, no peers: n/a


def test_sector_block_windows_start_on_exact_dates():
    d = pd.bdate_range("2025-12-01", periods=80)
    wide = pd.DataFrame({"XLK": np.linspace(100, 179, 80), "XLE": 100.0, "SPX": np.linspace(200, 239.5, 80)}, index=d)
    wide.loc[d[-2], "XLK"] = float("nan")  # Yahoo dropped one day for one series
    block = sector_block(wide)
    rows = {r["etf"]: r for r in block["rows"]}

    assert block["as_of"] == d[-1].strftime("%Y-%m-%d")
    assert rows["XLK"]["name"] == "Technology" and rows["SPX"]["name"] == "S&P 500"
    assert rows["XLK"]["ret_1d"] is None  # no close on the start day: n/a, not a two day move
    assert rows["XLK"]["ret_1w"] == round((179 / wide["XLK"].iloc[-6] - 1) * 100, 1)
    spx = wide["SPX"]
    assert rows["SPX"]["ret_1d"] == round((spx.iloc[-1] / spx.iloc[-2] - 1) * 100, 1)
    assert rows["XLE"]["ret_1d"] == 0.0
    last_2025 = spx[spx.index.year == 2025].iloc[-1]
    assert rows["SPX"]["ret_ytd"] == round((spx.iloc[-1] / last_2025 - 1) * 100, 1)
    assert rows["SPX"]["prior_2m"] == round((spx.iloc[-22] / spx.iloc[-64] - 1) * 100, 1)
    json.dumps(block, allow_nan=False)


def test_pe_growth_fit_recovers_a_line():
    g = [5.0, 10.0, 20.0, 30.0]
    comps = pd.DataFrame({"fwd_pe": [10 + 0.5 * x for x in g] + [-5.0], "growth": [x / 100 for x in g] + [0.1]})
    fit = pe_growth_fit(comps)  # the negative P/E is left out

    assert (fit["n"], fit["slope"], fit["intercept"], fit["r2"]) == (4, 0.5, 10.0, 1.0)
    assert pe_growth_fit(comps.head(2)) is None  # too few names for a line
