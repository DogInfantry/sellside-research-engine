import json

import pandas as pd

from export_dashboard_data import ticker_block
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
    assert len(block["reverse_dcf"]["sensitivity"]) == 16
    assert block["factors"]["valuation"] is None  # NaN becomes null, not a fake number
    assert block["rating"] == "BUY"
    json.dumps(block, allow_nan=False)  # raises if any NaN/inf leaks into the JSON
