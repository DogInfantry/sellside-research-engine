"""
valuation.py — Valuation framework: DCF, comps, football field.
Produces: DCF intrinsic value, sensitivity matrix, peer comps table,
football field data, bull/base/bear scenario valuations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple


# ─── WACC estimation ──────────────────────────────────────────────────────────

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
    cost_of_equity = risk_free_rate + beta * equity_risk_premium
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


# ─── comps / peer table ───────────────────────────────────────────────────────

def build_comps_table(research_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a peer comps table from the research dataset.
    Columns: ticker, sector, market_cap_bn, trailing_pe, forward_pe,
             ev_revenue (proxy), revenue_growth, net_margin, roe,
             ret_1m, ret_3m, research_score.
    """
    cols_needed = [
        "sector", "market_cap", "trailing_pe", "forward_pe",
        "revenue_growth", "net_margin", "roe",
        "ret_1m", "ret_3m",
    ]
    available = [c for c in cols_needed if c in research_df.columns]
    df = research_df[available].copy()

    if "market_cap" in df.columns:
        df["market_cap_bn"] = (df["market_cap"] / 1e9).round(1)
        df = df.drop(columns=["market_cap"])

    # Sort by sector then market_cap_bn descending
    sort_cols = []
    if "sector" in df.columns:
        sort_cols.append("sector")
    if "market_cap_bn" in df.columns:
        sort_cols.append("market_cap_bn")
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[True, False])

    # Compute sector-median PE ratio for relative valuation flag
    if "trailing_pe" in df.columns and "sector" in df.columns:
        sector_med_pe = df.groupby("sector")["trailing_pe"].transform("median")
        df["pe_vs_sector"] = ((df["trailing_pe"] / sector_med_pe) - 1).round(3)
        df["pe_vs_sector_label"] = df["pe_vs_sector"].apply(
            lambda x: f"+{x:.0%} prem" if x > 0.05 else (f"{x:.0%} disc" if x < -0.05 else "~par")
            if not pd.isna(x) else "N/A"
        )

    return df


def football_field(
    ticker: str,
    current_price: float,
    dcf_base: float,
    dcf_bull: float,
    dcf_bear: float,
    peer_median_pe_implied: Optional[float] = None,
    peer_low_pe_implied: Optional[float] = None,
    peer_high_pe_implied: Optional[float] = None,
    analyst_consensus_low: Optional[float] = None,
    analyst_consensus_mean: Optional[float] = None,
    analyst_consensus_high: Optional[float] = None,
    fifty_two_week_low: Optional[float] = None,
    fifty_two_week_high: Optional[float] = None,
) -> Dict:
    """
    Assemble football field data for visualization.
    Returns a dict of {methodology: (low, mid, high)} suitable for charting.
    """
    methods: Dict[str, Tuple[float, float, float]] = {}

    methods["DCF (Base Case)"] = (dcf_bear * 0.95, dcf_base, dcf_bull * 1.05)
    methods["DCF Scenarios (Bear/Base/Bull)"] = (dcf_bear, dcf_base, dcf_bull)

    if peer_low_pe_implied and peer_high_pe_implied:
        mid = peer_median_pe_implied or (peer_low_pe_implied + peer_high_pe_implied) / 2
        methods["Trading Comps (P/E)"] = (peer_low_pe_implied, mid, peer_high_pe_implied)

    if analyst_consensus_low and analyst_consensus_high:
        mid = analyst_consensus_mean or (analyst_consensus_low + analyst_consensus_high) / 2
        methods["Analyst Consensus Target"] = (analyst_consensus_low, mid, analyst_consensus_high)

    if fifty_two_week_low and fifty_two_week_high:
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


def derive_dcf_inputs(ticker_meta: Dict, sec_data: Dict) -> Dict:
    """
    Derive DCF inputs from available data.
    Uses net income as FCF proxy (× 0.80 capex haircut).
    Falls back gracefully where data is missing.
    """
    net_income = sec_data.get("net_income") or ticker_meta.get("netIncomeToCommon", 0)
    revenue_growth = sec_data.get("revenue_growth") or ticker_meta.get("revenueGrowth", 0.05)
    shares = sec_data.get("shares_outstanding") or ticker_meta.get("sharesOutstanding", 1)
    market_cap = ticker_meta.get("marketCap", 0)
    total_debt = ticker_meta.get("totalDebt", 0)
    total_cash = ticker_meta.get("totalCash", 0)
    beta_val = ticker_meta.get("beta", 1.0) or 1.0

    base_fcf = (net_income or 0) * 0.80
    net_debt = (total_debt or 0) - (total_cash or 0)
    wacc = estimate_wacc(beta=beta_val)

    return {
        "base_fcf": base_fcf,
        "base_growth": min(max(float(revenue_growth or 0.05), -0.20), 0.50),
        "wacc": wacc,
        "net_debt": net_debt,
        "shares_outstanding": max(float(shares or 1), 1),
        "market_cap": market_cap,
    }
