import pytest

from trg_workbench.analytics.valuation import dcf_valuation, reverse_dcf


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
