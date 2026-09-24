import json

import numpy as np
import pandas as pd
import pytest

from export_dashboard_data import (pe_growth_fit, quarterly_block, sector_block, sector_context, sentiment_block,
                                   spread_on_shared_dates, ticker_block)
from trg_workbench.analytics.valuation import build_comps_table
from trg_workbench.pipeline_v2 import value_bank, value_ticker


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


def test_value_ticker_grid_centers_on_own_wacc():
    sm = pd.DataFrame([{"ticker": "AAA", "net_income_to_common": 1e9, "shares_outstanding": 1e8, "beta": 1.2,
                        "target_low": 90.0, "target_mean": 110.0, "target_high": 130.0,
                        "fifty_two_week_low": 78.5, "fifty_two_week_high": 101.2}])
    px = pd.DataFrame({"AAA": np.linspace(80, 100, 300)}, index=pd.bdate_range("2025-06-02", periods=300))
    val = value_ticker("AAA", sm, pd.DataFrame(columns=["ticker"]), px, risk_free_rate=0.045)

    axes, grid = val["sensitivity_axes"], val["sensitivity_df"]
    i, j = axes["wacc"].index(val["inputs"]["wacc"]), axes["tg"].index(0.025)
    assert grid.iat[i, j] == val["scenarios"]["Base Case"]["intrinsic_value_per_share"]  # centre cell is the base DCF
    ff = val["football_field"]["methods"]
    assert ff["52-Week Range"] == (78.5, pytest.approx((78.5 + 101.2) / 2), 101.2)  # as quoted, not from adjusted closes
    assert val["sensitivity_axes"]["wacc"] == [round(val["inputs"]["wacc"] + d, 3) for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    assert ff["Analyst Consensus Target"] == (90.0, 110.0, 130.0)


def test_value_bank_residual_income():
    sm = pd.DataFrame([{"ticker": "BNK", "industry": "Banks - Diversified", "book_value": 100.0,
                        "return_on_equity": 0.15, "beta": 1.0, "target_low": 150.0, "target_mean": 170.0,
                        "target_high": 200.0}])
    px = pd.DataFrame({"BNK": [150.0, 160.0]})
    bank = value_bank("BNK", sm, px, risk_free_rate=0.045)

    r = bank["cost_of_equity"]
    assert bank["justified_pb"] == pytest.approx((0.15 - 0.025) / (r - 0.025))
    assert bank["actual_pb"] == pytest.approx(1.6)
    lo, mid, hi = bank["football_field"]["methods"]["Residual Income"]
    assert lo < mid < hi and mid == pytest.approx(bank["value_per_share"])  # cost of equity +1pp / base / -1pp
    assert value_bank("BNK", sm.assign(industry="Semiconductors"), px) is None  # not a bank: the DCF applies
    assert value_bank("BNK", sm.assign(book_value=float("nan")), px) is None


def test_quarterly_block_ttm_dupont_and_quality():
    q = pd.DataFrame({
        "period_end": pd.to_datetime(["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]),
        "revenue": [9e9, 10e9, 10e9, 10e9, 10e9], "eps": [1.0, 1.1, 1.2, 1.3, 1.4],
        "net_income": [1e9, 2e9, 2e9, 2e9, 2e9], "operating_income": [2e9, 3e9, 3e9, 3e9, 3e9],
        "ocf": [1e9, 2.5e9, 2.5e9, 2.5e9, 2.5e9], "capex": [-1e9, -1e9, -1e9, -1e9, -1e9],
        "total_assets": [None, None, None, None, 80e9], "equity": [None, None, None, None, 40e9],
    })
    balance_sheet_only = pd.DataFrame({"period_end": pd.to_datetime(["2025-03-31"]), "total_assets": [70e9], "equity": [35e9]})
    b = quarterly_block(pd.concat([balance_sheet_only, q]), bank=False)

    # Yahoo's balance sheet goes further back than its income statement: those dates are not quarters
    assert [x["period"] for x in b["quarters"]][-1] == "2026-06-30" and len(b["quarters"]) == 5
    assert b["quarters"][-1]["op_margin"] == 30.0 and b["quarters"][-1]["revenue_b"] == 10.0
    d = b["dupont"]  # TTM over the last 4 quarters, latest balance sheet
    assert (d["net_margin"], d["asset_turnover"], d["equity_multiplier"], d["roe"]) == (20.0, 0.5, 2.0, 20.0)
    assert b["quality"] == {"cfo_ni": 1.25, "capex_pct_revenue": 10.0, "fcf_margin": 15.0}
    bank = quarterly_block(q.assign(operating_income=None, capex=None), bank=True)
    assert bank["quality"] == {"cfo_ni": None, "capex_pct_revenue": None, "fcf_margin": None}  # CFO is funding, not earnings
    assert bank["quarters"][-1]["op_margin"] is None and bank["dupont"]["roe"] == 20.0
    broker = quarterly_block(q, bank=True)  # a broker that does report an operating income line
    assert all(x["op_margin"] is None for x in broker["quarters"])
    assert d["through"] == "2026-06-30"
    eps_only = pd.DataFrame({"period_end": pd.to_datetime(["2026-09-30"]), "eps": [1.5]})  # Yahoo half filled a quarter
    late = quarterly_block(pd.concat([q, eps_only]), bank=False)
    assert late["quarters"][-1]["eps"] == 1.5 and late["quarters"][-1]["revenue_b"] is None
    assert late["dupont"]["through"] == "2026-06-30" and late["dupont"]["roe"] == 20.0  # TTM on the last 4 complete quarters
    gap = quarterly_block(q.drop(index=2), bank=False)  # a missing quarter in the middle
    assert gap["dupont"]["roe"] is None  # 4 quarters that are not back to back are not a TTM
    short = quarterly_block(q.tail(3), bank=False)
    assert short["dupont"]["roe"] is None and short["quality"]["cfo_ni"] is None  # under 4 quarters: no TTM
    json.dumps(b, allow_nan=False)


def test_spread_on_shared_dates():
    d = pd.to_datetime(["2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23"])
    ten = pd.Series([4.90, 4.96, None, 5.11], index=d)  # Yahoo skipped 09-22
    two = pd.Series([4.70, 4.76, 4.71, None], index=d)  # FRED is a day behind
    date_, level, change = spread_on_shared_dates(ten, two)

    assert date_ == "2026-09-21"  # the last day both have
    assert level == pytest.approx(0.20) and change == pytest.approx(0.0)  # vs 09-18, the previous shared day
    assert spread_on_shared_dates(ten.head(1), two.tail(1)) == (None, None, None)


def test_sentiment_block_revisions_surprises_positioning():
    s = {
        "eps_trend": {"+1y": {"current": 15.0, "30daysAgo": 12.0, "90daysAgo": 12.5}},
        "eps_revisions": {"+1y": {"upLast30days": 42, "downLast30days": 1}},
        "surprises": [{"quarter": f"2026-0{m}-30", "actual": 1.0 + m / 10, "estimate": 1.0, "surprise_pct": 0.01 * m}
                      for m in range(1, 6)],
        "recommendations": [{"period": "-1m", "strongBuy": 9, "buy": 48, "hold": 2, "sell": 1, "strongSell": 0},
                            {"period": "0m", "strongBuy": 10, "buy": 48, "hold": 2, "sell": 1, "strongSell": 0}],
        # Yahoo's own % can carry the wrong sign (XOM: net +6.9M shares, -194.8%), so it is ignored
        "insider": {"purchases": 2.4e6, "sales": 6.2e6, "net_shares": -3.8e6, "held": 961.9e6, "net_pct": -1.948},
    }
    sm_row = {"short_pct_float": 0.0129, "short_ratio": 2.33, "shares_short": 110.0, "shares_short_prior": 100.0}
    b = sentiment_block(s, sm_row)

    assert (b["eps_next_fy"], b["rev_30d"], b["rev_90d"]) == (15.0, 25.0, 20.0)
    assert (b["up_30d"], b["down_30d"]) == (42, 1)
    assert [q["quarter"] for q in b["surprises"]] == ["2026-02-30", "2026-03-30", "2026-04-30", "2026-05-30"]  # last 4
    assert b["surprises"][-1]["surprise_pct"] == 5.0
    assert [r["period"] for r in b["recommendations"]] == ["-1m", "0m"] and b["recommendations"][-1]["strongBuy"] == 10
    # net as a % of what insiders held before the 6 months: -3.8M / (961.9M + 3.8M)
    assert b["insider"] == {"purchases": 2400000, "sales": 6200000, "net_shares": -3800000, "net_pct": -0.4}
    assert b["short"] == {"pct_float": 1.29, "days_to_cover": 2.3, "change_pct": 10.0}

    loss = sentiment_block({"eps_trend": {"+1y": {"current": 0.5, "30daysAgo": -0.2, "90daysAgo": 0.0}}}, {})
    assert loss["rev_30d"] is None and loss["rev_90d"] is None  # a % change from a loss or zero base means nothing
    empty = sentiment_block(None, {})
    assert empty["surprises"] == [] and empty["short"]["pct_float"] is None and empty["up_30d"] is None
    json.dumps(b, allow_nan=False)
