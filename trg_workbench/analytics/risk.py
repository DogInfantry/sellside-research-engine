"""
risk.py — Risk metrics for sell-side research engine
Computes: realized vol, beta, Sharpe, Sortino, max drawdown,
VaR, CVaR, correlation matrix, risk-return summary table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple

TRADING_DAYS = 252
RISK_FREE_RATE = 0.053  # approximate current US risk-free rate


# ─── core computations ────────────────────────────────────────────────────────

def _daily_returns(prices: pd.Series) -> pd.Series:
    """Log returns, NaN-dropped."""
    return np.log(prices / prices.shift(1)).dropna()


def realized_vol(prices: pd.Series, window: int = 21) -> float:
    """Annualized realized volatility over the last `window` trading days."""
    rets = _daily_returns(prices).tail(window)
    if len(rets) < 5:
        return float("nan")
    return float(rets.std() * np.sqrt(TRADING_DAYS))


def beta(
    prices: pd.Series,
    market_prices: pd.Series,
    window: int = 63,
) -> float:
    """OLS beta vs. market over trailing `window` days."""
    rets = _daily_returns(prices).tail(window)
    mkt = _daily_returns(market_prices).tail(window)
    aligned = pd.concat([rets, mkt], axis=1).dropna()
    if len(aligned) < 20:
        return float("nan")
    cov = aligned.cov().iloc[0, 1]
    var = aligned.iloc[:, 1].var()
    return float(cov / var) if var > 1e-12 else float("nan")


def sharpe_ratio(prices: pd.Series, rfr: float = RISK_FREE_RATE) -> float:
    """Annualized Sharpe ratio."""
    rets = _daily_returns(prices)
    if len(rets) < 20:
        return float("nan")
    excess = rets - rfr / TRADING_DAYS
    if excess.std() < 1e-12:
        return float("nan")
    return float(excess.mean() / excess.std() * np.sqrt(TRADING_DAYS))


def sortino_ratio(prices: pd.Series, rfr: float = RISK_FREE_RATE) -> float:
    """Annualized Sortino ratio (downside deviation denominator)."""
    rets = _daily_returns(prices)
    if len(rets) < 20:
        return float("nan")
    excess = rets - rfr / TRADING_DAYS
    downside = excess[excess < 0]
    if len(downside) < 5 or downside.std() < 1e-12:
        return float("nan")
    return float(excess.mean() / downside.std() * np.sqrt(TRADING_DAYS))


def max_drawdown(prices: pd.Series) -> float:
    """Maximum peak-to-trough drawdown (negative number)."""
    if prices.empty:
        return float("nan")
    roll_max = prices.cummax()
    drawdowns = (prices - roll_max) / roll_max
    return float(drawdowns.min())


def historical_var_cvar(
    prices: pd.Series,
    confidence: float = 0.95,
    window: int = 252,
) -> Tuple[float, float]:
    """
    Historical (non-parametric) VaR and CVaR.
    Returns (VaR, CVaR) as positive loss magnitudes at given confidence level.
    """
    rets = _daily_returns(prices).tail(window)
    if len(rets) < 20:
        return float("nan"), float("nan")
    cutoff = np.percentile(rets, (1 - confidence) * 100)
    var = float(-cutoff)
    cvar = float(-rets[rets <= cutoff].mean())
    return var, cvar


def correlation_matrix(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Spearman rank correlation of daily log-returns."""
    rets = np.log(prices_df / prices_df.shift(1)).dropna()
    return rets.corr(method="spearman").round(3)


# ─── aggregate risk table ─────────────────────────────────────────────────────

def build_risk_table(
    prices_df: pd.DataFrame,
    market_col: str = "SPY",
    rfr: float = RISK_FREE_RATE,
) -> pd.DataFrame:
    """
    Build a per-ticker risk summary table with columns:
    vol_21d, vol_63d, beta, sharpe, sortino, max_drawdown,
    var_95, cvar_95, ret_ytd, ret_1y.

    Args:
        prices_df: Wide DataFrame (date index, ticker columns), must include `market_col`.
        market_col: Ticker used as market proxy (default 'SPY').
        rfr: Annual risk-free rate (decimal).
    """
    if market_col not in prices_df.columns:
        # fall back gracefully — compute beta as NaN
        mkt = pd.Series(dtype=float)
    else:
        mkt = prices_df[market_col]

    rows: list[Dict] = []
    for ticker in prices_df.columns:
        if ticker == market_col:
            continue
        px = prices_df[ticker].dropna()
        if px.empty:
            continue

        var95, cvar95 = historical_var_cvar(px)

        ret_ytd = float("nan")
        ret_1y = float("nan")
        if len(px) >= 2:
            # YTD from Jan 1 approximate (first available in year)
            this_year = px.last("365D")
            if len(this_year) >= 2:
                ret_1y = float((this_year.iloc[-1] / this_year.iloc[0]) - 1)
            ytd_start = px[px.index >= pd.Timestamp(px.index[-1].year, 1, 1)]
            if len(ytd_start) >= 2:
                ret_ytd = float((ytd_start.iloc[-1] / ytd_start.iloc[0]) - 1)

        rows.append(
            {
                "ticker": ticker,
                "vol_21d": round(realized_vol(px, 21), 4),
                "vol_63d": round(realized_vol(px, 63), 4),
                "beta": round(beta(px, mkt, 63) if not mkt.empty else float("nan"), 3),
                "sharpe": round(sharpe_ratio(px, rfr), 3),
                "sortino": round(sortino_ratio(px, rfr), 3),
                "max_drawdown": round(max_drawdown(px), 4),
                "var_95_1d": round(var95, 4),
                "cvar_95_1d": round(cvar95, 4),
                "ret_ytd": round(ret_ytd, 4) if not np.isnan(ret_ytd) else float("nan"),
                "ret_1y": round(ret_1y, 4) if not np.isnan(ret_1y) else float("nan"),
            }
        )

    df = pd.DataFrame(rows).set_index("ticker")
    df = df.sort_values("sharpe", ascending=False)
    return df


def risk_tier(sharpe: float, vol: float) -> str:
    """Assign a qualitative risk tier for report narrative."""
    if np.isnan(sharpe) or np.isnan(vol):
        return "N/A"
    if sharpe >= 1.5 and vol <= 0.25:
        return "High Quality / Low Risk"
    if sharpe >= 0.8 and vol <= 0.35:
        return "Moderate Risk"
    if sharpe < 0 or vol > 0.50:
        return "High Risk / Speculative"
    return "Average Risk"
