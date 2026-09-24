import pandas as pd
import pytest

from trg_workbench.analytics.valuation import (build_comps_table, capm_cost_of_equity, dcf_valuation, derive_dcf_inputs,
                                               estimate_wacc, football_field, residual_income_value, reverse_dcf)


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
        {**eq, "ticker": "LOS", "industry": "Software", "forward_pe": -12.0, "enterprise_value": -5.0,
         "ebitda": 1.0, "total_revenue": 4.0, "eps_growth_next_year": 0.5},
        {"ticker": "XLK", "instrument_group": "sector_proxy", "forward_pe": 99.0},
    ])
    c = build_comps_table(sm).set_index("ticker")

    assert list(c.index) == ["AAA", "BNK", "AM", "LOS"]  # ETF rows are not comps
    a = c.loc["AAA"]
    assert (a.fwd_pe, a.ev_ebitda, a.ev_sales, a.net_debt_ebitda) == (20, 10, 2.5, 2)
    assert a.peg == pytest.approx(0.8)  # 20x over 25% EPS growth
    assert (a.growth, a.margin, a.roe) == (0.2, 0.3, 0.4)
    # a bank's EV is not an enterprise value, and falling EPS has no PEG
    assert c.loc["BNK", ["ev_ebitda", "ev_sales", "net_debt_ebitda", "peg"]].isna().all()
    assert c.loc["BNK", "fwd_pe"] == 12
    assert c.loc["AM", "ev_ebitda"] == 10  # asset managers keep EV multiples
    assert pd.isna(c.loc["AM", "fwd_pe"])  # missing stays missing
    # a loss maker has no P/E and a cash rich negative EV no EV multiple: n/a, not a deep discount
    assert c.loc["LOS", ["fwd_pe", "peg", "ev_ebitda", "ev_sales"]].isna().all()
    old_cache = build_comps_table(pd.DataFrame([{"ticker": "Z", "instrument_group": "us_equity"}]))
    assert old_cache[["fwd_pe", "ev_ebitda"]].isna().all(axis=None)  # no new columns yet: n/a, not KeyError


def test_live_risk_free_rate_flows_into_wacc_and_cost_of_equity():
    sm_row = {"net_income_to_common": 50.0, "shares_outstanding": 10.0, "beta": 1.0}
    live = derive_dcf_inputs(sm_row, {}, risk_free_rate=0.045)

    assert live["cost_of_equity"] == pytest.approx(capm_cost_of_equity(1.0, 0.045))  # Blume beta of 1 is 1
    assert live["wacc"] == estimate_wacc(beta=1.0, risk_free_rate=0.045)
    assert live["wacc"] < derive_dcf_inputs(sm_row, {})["wacc"]  # 4.5% Rf vs the old 5.3% default


def test_residual_income_is_book_times_justified_pb():
    ri = residual_income_value(book_value_ps=100.0, roe=0.15, cost_of_equity=0.10, growth=0.025)
    assert ri["justified_pb"] == pytest.approx(0.125 / 0.075)
    assert ri["value_per_share"] == pytest.approx(100 * 0.125 / 0.075)
    assert residual_income_value(float("nan"), 0.15, 0.10) is None  # no book value: n/a
    assert residual_income_value(100.0, 0.02, 0.10) is None  # ROE below growth: the model says nothing useful
    assert residual_income_value(100.0, 0.15, 0.028) is None  # r too close to g: value explodes


def test_football_field_uses_only_real_ranges():
    ff = football_field("X", 100.0, dcf_base=110.0, dcf_bull=140.0, dcf_bear=80.0,
                        analyst_consensus_low=90.0, analyst_consensus_mean=120.0, analyst_consensus_high=150.0,
                        fifty_two_week_low=70.0, fifty_two_week_high=130.0)
    assert list(ff["methods"]) == ["DCF Scenarios (Bear/Base/Bull)", "Analyst Consensus Target", "52-Week Range"]
    assert ff["methods"]["DCF Scenarios (Bear/Base/Bull)"] == (80.0, 110.0, 140.0)  # no padded +-5% row
    bank = football_field("B", 100.0, residual_income=(85.0, 95.0, 110.0), analyst_consensus_low=float("nan"))
    assert list(bank["methods"]) == ["Residual Income"]  # a NaN target is not a range
