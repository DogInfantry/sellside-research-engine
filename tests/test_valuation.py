import pandas as pd
import pytest

from trg_workbench.analytics.valuation import build_comps_table, dcf_valuation, derive_dcf_inputs, estimate_wacc, reverse_dcf


def test_reverse_dcf_recovers_known_growth_rate():
    base_fcf = 100.0
    growth_rate = 0.08
    wacc = 0.10
    terminal_growth = 0.03
    shares = 10.0
    net_debt = 50.0

    forward_dcf = dcf_valuation(
        base_fcf=base_fcf,
        growth_rates=[growth_rate] * 10,
        terminal_growth_rate=terminal_growth,
        wacc=wacc,
        net_debt=net_debt,
        shares_outstanding=shares,
    )

    result = reverse_dcf(
        current_price=forward_dcf["intrinsic_value_per_share"],
        shares_outstanding=shares,
        net_debt=net_debt,
        base_fcf=base_fcf,
        wacc=wacc,
        terminal_growth=terminal_growth,
    )

    assert result["implied_growth_rate"] == pytest.approx(growth_rate, abs=0.001)
    assert result["implied_ev"] > result["target_equity_value"]
    assert set(result["sensitivity"]) == {"wacc_down_100bps", "base", "wacc_up_100bps"}


def test_reverse_dcf_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        reverse_dcf(
            current_price=100.0,
            shares_outstanding=10.0,
            net_debt=0.0,
            base_fcf=100.0,
            wacc=0.03,
            terminal_growth=0.03,
        )


def test_derive_dcf_inputs_reads_snake_case_security_master():
    sm_row = {"market_cap": 500.0, "total_debt": 80.0, "total_cash": 30.0, "beta": 1.4,
              "net_income_to_common": 50.0, "revenue_growth": 0.1, "shares_outstanding": 10.0}
    inputs = derive_dcf_inputs(sm_row, {"net_income": float("nan")})  # NaN as read from CSV

    assert inputs["net_debt"] == 50.0
    assert inputs["market_cap"] == 500.0
    assert inputs["wacc"] == estimate_wacc(beta=0.67 * 1.4 + 0.33)  # Blume adjusted
    assert inputs["base_fcf"] == pytest.approx(40.0)
    assert inputs["shares_outstanding"] == 10.0
    assert derive_dcf_inputs({**sm_row, "sector": "Financial Services"}, {})["net_debt"] == 0


def test_derive_dcf_inputs_prefers_consensus_growth_and_all_class_shares():
    # CVX style one off: trailing +53.5% (deal + oil) vs consensus -6.8%; GOOGL style SEC shares count one class
    sm_row = {"net_income_to_common": 50.0, "revenue_growth": 0.535, "revenue_growth_next_year": -0.068,
              "shares_outstanding": 12.1}
    inputs = derive_dcf_inputs(sm_row, {"revenue_growth": 0.535, "shares_outstanding": 5.87})

    assert inputs["base_growth"] == pytest.approx(-0.068)
    assert inputs["consensus_growth"] == pytest.approx(-0.068)
    assert inputs["shares_outstanding"] == 12.1


def test_build_comps_table_multiples_and_balance_sheet_names():
    eq = {"instrument_group": "us_equity", "sector": "Technology"}
    sm = pd.DataFrame([
        {**eq, "ticker": "AAA", "industry": "Semiconductors", "forward_pe": 20.0, "enterprise_value": 1000.0,
         "ebitda": 100.0, "total_revenue": 400.0, "eps_growth_next_year": 0.25, "revenue_growth_next_year": 0.2,
         "profit_margins": 0.3, "return_on_equity": 0.4, "total_debt": 300.0, "total_cash": 100.0},
        {**eq, "ticker": "BNK", "sector": "Financial Services", "industry": "Banks - Diversified", "forward_pe": 12.0,
         "enterprise_value": 50.0, "ebitda": None, "total_revenue": 100.0, "eps_growth_next_year": -0.1,
         "total_debt": 900.0, "total_cash": 10.0},
        {**eq, "ticker": "AM", "sector": "Financial Services", "industry": "Asset Management",
         "enterprise_value": 200.0, "ebitda": 20.0, "total_revenue": 50.0},
        {"ticker": "XLK", "instrument_group": "sector_proxy", "forward_pe": 99.0},
    ])
    c = build_comps_table(sm).set_index("ticker")

    assert list(c.index) == ["AAA", "BNK", "AM"]  # ETF rows are not comps
    a = c.loc["AAA"]
    assert (a.fwd_pe, a.ev_ebitda, a.ev_sales, a.net_debt_ebitda) == (20, 10, 2.5, 2)
    assert a.peg == pytest.approx(0.8)  # 20x over 25% EPS growth
    assert (a.growth, a.margin, a.roe) == (0.2, 0.3, 0.4)
    # a bank's EV is not an enterprise value, and falling EPS has no PEG
    assert c.loc["BNK", ["ev_ebitda", "ev_sales", "net_debt_ebitda", "peg"]].isna().all()
    assert c.loc["BNK", "fwd_pe"] == 12
    assert c.loc["AM", "ev_ebitda"] == 10  # asset managers keep EV multiples
    assert pd.isna(c.loc["AM", "fwd_pe"])  # missing stays missing
    old_cache = build_comps_table(pd.DataFrame([{"ticker": "Z", "instrument_group": "us_equity"}]))
    assert old_cache[["fwd_pe", "ev_ebitda"]].isna().all(axis=None)  # no new columns yet: n/a, not KeyError
