import pytest

from trg_workbench.analytics.valuation import dcf_valuation, derive_dcf_inputs, estimate_wacc, reverse_dcf


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
