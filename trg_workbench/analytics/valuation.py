"""
valuation.py — Valuation framework: DCF, comps, football field.
Produces: DCF intrinsic value, sensitivity matrix, peer comps table,
football field data, bull/base/bear scenario valuations.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import brentq


# ─── WACC estimation ──────────────────────────────────────────────────────────

def capm_cost_of_equity(beta: float, risk_free_rate: float = 0.053, equity_risk_premium: float = 0.055) -> float:
    """CAPM: Re = Rf + beta x ERP."""
    return risk_free_rate + beta * equity_risk_premium


def estimate_wacc(
    beta: float = 1.0,
    risk_free_rate: float = 0.053,
    equity_risk_premium: float = 0.055,
    tax_rate: float = 0.21,
    debt_to_equity: float = 0.30,
    cost_of_debt: float = 0.06,
) -> float:
    """
    CAPM-based WACC.
    WACC = (E/V) * Re + (D/V) * Rd * (1 - Tc)
    """
    cost_of_equity = capm_cost_of_equity(beta, risk_free_rate, equity_risk_premium)
    # D/E given → D/V = (D/E) / (1 + D/E), E/V = 1 / (1 + D/E)
    de = debt_to_equity
    e_weight = 1 / (1 + de)
    d_weight = de / (1 + de)
    wacc = e_weight * cost_of_equity + d_weight * cost_of_debt * (1 - tax_rate)
    return round(wacc, 4)


# ─── DCF engine ──────────────────────────────────────────────────────────────

def dcf_valuation(
    base_fcf: float,
    growth_rates: List[float],  # explicit rate for each forecast year
    terminal_growth_rate: float,
    wacc: float,
    net_debt: float = 0.0,
    shares_outstanding: float = 1.0,
) -> Dict:
    """
    Multi-stage DCF → equity value per share.

    Args:
        base_fcf: Most recent annual free cash flow (proxy: net_income * 0.8 if FCF unavailable).
        growth_rates: List of growth rates for each explicit forecast year (e.g. [0.15, 0.12, 0.10, 0.09, 0.08]).
        terminal_growth_rate: Long-run FCF growth rate for Gordon Growth terminal value.
        wacc: Discount rate.
        net_debt: Total debt minus cash (enterprise value → equity bridge).
        shares_outstanding: For per-share value.

    Returns dict with: pv_fcfs, terminal_value, enterprise_value, equity_value, intrinsic_value_per_share.
    """
    if wacc <= terminal_growth_rate:
        terminal_growth_rate = wacc - 0.01  # guard division by zero

    fcfs: List[float] = []
    pv_fcfs: List[float] = []
    cf = base_fcf
    for t, g in enumerate(growth_rates, start=1):
        cf = cf * (1 + g)
        fcfs.append(cf)
        pv = cf / (1 + wacc) ** t
        pv_fcfs.append(pv)

    terminal_value = fcfs[-1] * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    pv_terminal = terminal_value / (1 + wacc) ** len(growth_rates)

    enterprise_value = sum(pv_fcfs) + pv_terminal
    equity_value = enterprise_value - net_debt
    intrinsic = equity_value / shares_outstanding if shares_outstanding > 0 else float("nan")

    return {
        "fcf_projections": [round(f, 0) for f in fcfs],
        "pv_fcfs": [round(p, 0) for p in pv_fcfs],
        "pv_terminal": round(pv_terminal, 0),
        "terminal_value": round(terminal_value, 0),
        "enterprise_value": round(enterprise_value, 0),
        "equity_value": round(equity_value, 0),
        "intrinsic_value_per_share": round(intrinsic, 2),
        "wacc_used": wacc,
        "tgr_used": terminal_growth_rate,
        "terminal_pct_of_ev": round(pv_terminal / enterprise_value, 3) if enterprise_value != 0 else float("nan"),
    }


def dcf_sensitivity(
    base_fcf: float,
    growth_rates: List[float],
    net_debt: float,
    shares_outstanding: float,
    wacc_range: Optional[List[float]] = None,
    tgr_range: Optional[List[float]] = None,
) -> pd.DataFrame:
    """
    Sensitivity table: rows = WACC values, cols = terminal growth rates.
    Cell value = implied intrinsic value per share.
    """
    if wacc_range is None:
        wacc_range = [0.07, 0.08, 0.09, 0.10, 0.11, 0.12]
    if tgr_range is None:
        tgr_range = [0.01, 0.02, 0.025, 0.03, 0.035, 0.04]

    results = {}
    for tgr in tgr_range:
        col = {}
        for wacc in wacc_range:
            if wacc <= tgr:
                col[f"{wacc:.1%}"] = float("nan")
            else:
                res = dcf_valuation(base_fcf, growth_rates, tgr, wacc, net_debt, shares_outstanding)
                col[f"{wacc:.1%}"] = res["intrinsic_value_per_share"]
        results[f"TGR {tgr:.1%}"] = col

    df = pd.DataFrame(results)
    df.index.name = "WACC"
    return df.round(2)


def _enterprise_value_for_constant_growth(
    base_fcf: float,
    growth_rate: float,
    wacc: float,
    terminal_growth: float,
    projection_years: int,
) -> float:
    if wacc <= terminal_growth:
        raise ValueError("wacc must be greater than terminal_growth")

    fcfs = [
        base_fcf * (1 + growth_rate) ** year
        for year in range(1, projection_years + 1)
    ]
    pv_fcfs = [
        fcf / (1 + wacc) ** year
        for year, fcf in enumerate(fcfs, start=1)
    ]
    terminal_value = fcfs[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1 + wacc) ** projection_years
    return float(sum(pv_fcfs) + pv_terminal)


def reverse_dcf(
    current_price: float,
    shares_outstanding: float,
    net_debt: float,
    base_fcf: float,
    wacc: float,
    terminal_growth: float,
    projection_years: int = 10,
) -> Dict:
    """
    Solve for the constant annual FCF growth rate implied by the current share price.

    Returns a dict with the implied growth rate, target enterprise value, and
    WACC sensitivity using +/- 100 bps around the base WACC.
    """
    if current_price <= 0:
        raise ValueError("current_price must be positive")
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive")
    if base_fcf <= 0:
        raise ValueError("base_fcf must be positive")
    if projection_years <= 0:
        raise ValueError("projection_years must be positive")
    if wacc <= terminal_growth:
        raise ValueError("wacc must be greater than terminal_growth")

    target_equity_value = current_price * shares_outstanding
    implied_ev = target_equity_value + net_debt

    def solve_for_wacc(discount_rate: float, *, allow_nan: bool = False) -> float:
        if discount_rate <= terminal_growth:
            return float("nan")

        def objective(growth_rate: float) -> float:
            return (
                _enterprise_value_for_constant_growth(
                    base_fcf=base_fcf,
                    growth_rate=growth_rate,
                    wacc=discount_rate,
                    terminal_growth=terminal_growth,
                    projection_years=projection_years,
                )
                - implied_ev
            )

        lower = -0.90
        upper = 1.00
        for candidate_upper in [upper, 1.50, 2.00, 3.00, 5.00]:
            if objective(lower) * objective(candidate_upper) <= 0:
                return float(brentq(objective, lower, candidate_upper))
        if allow_nan:
            return float("nan")
        raise ValueError("could not bracket implied growth rate")

    implied_growth_rate = solve_for_wacc(wacc)
    sensitivity = {
        "wacc_down_100bps": {
            "wacc": round(wacc - 0.01, 4),
            "implied_growth_rate": round(solve_for_wacc(wacc - 0.01, allow_nan=True), 4),
        },
        "base": {
            "wacc": round(wacc, 4),
            "implied_growth_rate": round(implied_growth_rate, 4),
        },
        "wacc_up_100bps": {
            "wacc": round(wacc + 0.01, 4),
            "implied_growth_rate": round(solve_for_wacc(wacc + 0.01, allow_nan=True), 4),
        },
    }

    return {
        "implied_growth_rate": round(implied_growth_rate, 4),
        "implied_ev": round(implied_ev, 0),
        "target_equity_value": round(target_equity_value, 0),
        "current_price": current_price,
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "projection_years": projection_years,
        "sensitivity": sensitivity,
    }


# ─── comps / peer table ───────────────────────────────────────────────────────

# balance sheet businesses: debt and cash are operating items, so no FCF DCF and no EV multiples
BALANCE_SHEET_INDUSTRIES = ("Banks", "Capital Markets", "Insurance")


def build_comps_table(security_master: pd.DataFrame) -> pd.DataFrame:
    """
    Peer comps for the US stock universe from the yfinance security master (TTM, same basis for every name).
    Columns: ticker, sector, fwd_pe, ev_ebitda, ev_sales, peg, growth, margin, roe, net_debt_ebitda.
    Missing inputs stay NaN (shown as n/a); the page compares each metric with the sector peer median.
    """
    cols = ["ticker", "sector", "industry", "forward_pe", "enterprise_value", "ebitda", "total_revenue",
            "eps_growth_next_year", "revenue_growth_next_year", "profit_margins", "return_on_equity",
            "total_debt", "total_cash"]
    df = security_master[security_master["instrument_group"] == "us_equity"].reindex(columns=cols)
    col = lambda c: pd.to_numeric(df[c], errors="coerce")
    bank = df["industry"].astype(str).str.startswith(BALANCE_SHEET_INDUSTRIES)
    # loss makers have no P/E and cash rich names a negative EV: n/a, not a deep discount
    fwd = col("forward_pe").where(lambda s: np.isfinite(s) & (s > 0))
    ev = col("enterprise_value").mask(bank).where(lambda s: s > 0)
    ebitda = col("ebitda").where(col("ebitda") > 0)
    eps_growth = col("eps_growth_next_year")
    return pd.DataFrame({
        "ticker": df["ticker"],
        "sector": df["sector"],
        "fwd_pe": fwd,
        "ev_ebitda": ev / ebitda,
        "ev_sales": ev / col("total_revenue"),
        "peg": fwd / (eps_growth * 100).where(eps_growth > 0),
        "growth": col("revenue_growth_next_year"),
        "margin": col("profit_margins"),
        "roe": col("return_on_equity"),
        "net_debt_ebitda": (col("total_debt") - col("total_cash")).mask(bank) / ebitda,
    }).reset_index(drop=True)


def football_field(
    ticker: str,
    current_price: float,
    dcf_base: Optional[float] = None,
    dcf_bull: Optional[float] = None,
    dcf_bear: Optional[float] = None,
    peer_median_pe_implied: Optional[float] = None,
    peer_low_pe_implied: Optional[float] = None,
    peer_high_pe_implied: Optional[float] = None,
    analyst_consensus_low: Optional[float] = None,
    analyst_consensus_mean: Optional[float] = None,
    analyst_consensus_high: Optional[float] = None,
    fifty_two_week_low: Optional[float] = None,
    fifty_two_week_high: Optional[float] = None,
    residual_income: Optional[Tuple[float, float, float]] = None,
) -> Dict:
    """
    Assemble football field data for visualization.
    Returns a dict of {methodology: (low, mid, high)} suitable for charting. Only real ranges: a method
    whose inputs are missing (None or NaN) is left out, never padded.
    """
    ok = lambda *xs: all(x is not None and not pd.isna(x) for x in xs)
    methods: Dict[str, Tuple[float, float, float]] = {}

    if ok(dcf_bear, dcf_base, dcf_bull):
        methods["DCF Scenarios (Bear/Base/Bull)"] = (dcf_bear, dcf_base, dcf_bull)
    if residual_income and ok(*residual_income):
        methods["Residual Income"] = tuple(residual_income)

    if ok(peer_low_pe_implied, peer_high_pe_implied):
        mid = peer_median_pe_implied or (peer_low_pe_implied + peer_high_pe_implied) / 2
        methods["Trading Comps (P/E)"] = (peer_low_pe_implied, mid, peer_high_pe_implied)

    if ok(analyst_consensus_low, analyst_consensus_high):
        mid = analyst_consensus_mean if ok(analyst_consensus_mean) else (analyst_consensus_low + analyst_consensus_high) / 2
        methods["Analyst Consensus Target"] = (analyst_consensus_low, mid, analyst_consensus_high)

    if ok(fifty_two_week_low, fifty_two_week_high):
        mid52 = (fifty_two_week_low + fifty_two_week_high) / 2
        methods["52-Week Range"] = (fifty_two_week_low, mid52, fifty_two_week_high)

    return {
        "ticker": ticker,
        "current_price": current_price,
        "methods": methods,
    }


# ─── scenario analysis ────────────────────────────────────────────────────────

def scenario_analysis(
    base_fcf: float,
    base_growth: float,
    wacc: float,
    net_debt: float,
    shares_outstanding: float,
) -> Dict[str, Dict]:
    """
    Three-scenario DCF: bear, base, bull.
    Bull: growth +30%, TGR +0.5%, WACC -0.5%
    Base: as given, TGR = 2.5%
    Bear: growth -30%, TGR 1%, WACC +1%
    """
    base_rates = [base_growth * (0.85 ** i) for i in range(5)]

    scenarios = {
        "Bear Case": {
            "growth_rates": [g * 0.70 for g in base_rates],
            "tgr": 0.010,
            "wacc": min(wacc + 0.01, 0.15),
        },
        "Base Case": {
            "growth_rates": base_rates,
            "tgr": 0.025,
            "wacc": wacc,
        },
        "Bull Case": {
            "growth_rates": [g * 1.30 for g in base_rates],
            "tgr": 0.035,
            "wacc": max(wacc - 0.005, 0.06),
        },
    }

    results = {}
    for name, params in scenarios.items():
        r = dcf_valuation(
            base_fcf,
            params["growth_rates"],
            params["tgr"],
            params["wacc"],
            net_debt,
            shares_outstanding,
        )
        results[name] = r

    return results


def residual_income_value(book_value_ps: float, roe: float, cost_of_equity: float, growth: float = 0.025) -> Optional[Dict]:
    """
    Single stage residual income (CFA L2): V0 = B0 x (ROE - g) / (r - g), so the multiple is the justified P/B.
    None when book value or ROE is missing, ROE is not above g, or r is within 0.5pp of g (value explodes).
    """
    if any(x is None or pd.isna(x) for x in (book_value_ps, roe)) or book_value_ps <= 0 or roe <= growth:
        return None
    if cost_of_equity - growth < 0.005:
        return None
    justified_pb = (roe - growth) / (cost_of_equity - growth)
    return {"justified_pb": justified_pb, "value_per_share": book_value_ps * justified_pb}


def derive_dcf_inputs(ticker_meta: Dict, sec_data: Dict, risk_free_rate: float = 0.053) -> Dict:
    """
    Derive DCF inputs from available data.
    Uses net income as FCF proxy (× 0.80 capex haircut).
    Falls back gracefully where data is missing.
    """
    def pick(d: Dict, *keys, default=None):
        # security master is snake_case; camelCase kept for raw yfinance info. Skips None/NaN.
        return next((d[k] for k in keys if d.get(k) is not None and not pd.isna(d[k])), default)

    net_income = pick(sec_data, "net_income") or pick(ticker_meta, "net_income_to_common", "netIncomeToCommon", default=0)
    # consensus +1y revenue growth first: trailing growth carries one offs (M&A, commodity swings) into 5 years
    consensus_growth = pick(ticker_meta, "revenue_growth_next_year")
    revenue_growth = consensus_growth or pick(sec_data, "revenue_growth") or pick(ticker_meta, "revenue_growth", "revenueGrowth", default=0.05)
    # security master shares first: it holds all share classes (GOOGL, META); SEC dei counts one class
    shares = pick(ticker_meta, "shares_outstanding", "sharesOutstanding") or pick(sec_data, "shares_outstanding", default=1)
    market_cap = pick(ticker_meta, "market_cap", "marketCap", default=0)
    total_debt = pick(ticker_meta, "total_debt", "totalDebt", default=0)
    total_cash = pick(ticker_meta, "total_cash", "totalCash", default=0)
    # ponytail: Blume adjusted beta (Bloomberg ADJ BETA), shrinks raw beta toward 1; industry betas are the upgrade
    beta_val = 0.67 * (pick(ticker_meta, "beta", default=1.0) or 1.0) + 0.33

    base_fcf = (net_income or 0) * 0.80
    net_debt = (total_debt or 0) - (total_cash or 0)
    # ponytail: bank debt/cash is operating balance sheet (JEF cash > 6x mcap), so no bridge for financials; also zeroes BLK/LAZ small corporate net debt
    if ticker_meta.get("sector") == "Financial Services":
        net_debt = 0
    wacc = estimate_wacc(beta=beta_val, risk_free_rate=risk_free_rate)

    return {
        "base_fcf": base_fcf,
        "base_growth": min(max(float(revenue_growth or 0.05), -0.20), 0.50),
        "consensus_growth": consensus_growth,
        "wacc": wacc,
        "net_debt": net_debt,
        "shares_outstanding": max(float(shares or 1), 1),
        "market_cap": market_cap,
        "risk_free_rate": risk_free_rate,
        "cost_of_equity": capm_cost_of_equity(beta_val, risk_free_rate),
    }
