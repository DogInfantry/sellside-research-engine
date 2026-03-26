from __future__ import annotations

from datetime import date

import pandas as pd


RETURN_WINDOWS = {
    "ret_1d": 1,
    "ret_1w": 5,
    "ret_1m": 21,
    "ret_3m": 63,
}


def _window_return(series: pd.Series, window: int) -> float | None:
    clean = series.dropna()
    if len(clean) <= window:
        return None
    latest = clean.iloc[-1]
    previous = clean.iloc[-(window + 1)]
    if previous == 0:
        return None
    return float((latest / previous) - 1)


def build_price_snapshot(prices: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    subset = prices.loc[pd.to_datetime(prices["date"]).dt.date <= as_of_date].copy()
    if subset.empty:
        return pd.DataFrame()

    subset["date"] = pd.to_datetime(subset["date"])

    def summarize(group: pd.DataFrame) -> pd.Series:
        ordered = group.sort_values("date")
        latest = ordered.iloc[-1]
        payload = {
            "ticker": group.name,
            "price_date": latest["date"],
            "close": latest["close"],
            "volume": latest.get("volume"),
        }
        close_series = ordered["close"].astype("float64")
        for label, window in RETURN_WINDOWS.items():
            payload[label] = _window_return(close_series, window)
        return pd.Series(payload)

    snapshot = subset.groupby("ticker", group_keys=False).apply(summarize, include_groups=False)
    return snapshot.reset_index(drop=True)


def _percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").replace([float("inf"), float("-inf")], pd.NA)
    if clean.dropna().empty:
        return pd.Series([float("nan")] * len(series), index=series.index, dtype="float64")
    return clean.rank(pct=True, ascending=higher_is_better)


def build_research_dataset(
    fundamentals: pd.DataFrame,
    prices: pd.DataFrame,
    metadata: pd.DataFrame,
    as_of_date: date,
    analyst_views: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if fundamentals.empty or prices.empty:
        return pd.DataFrame()

    price_snapshot = build_price_snapshot(prices, as_of_date)
    equity_metadata = metadata.loc[metadata["instrument_group"] == "us_equity"].copy()
    metadata_columns = [
        "ticker",
        "long_name",
        "sector",
        "industry",
        "currency",
        "exchange",
        "forward_pe",
        "eps_avg_current_year",
        "eps_growth_current_year",
        "eps_avg_next_year",
        "eps_growth_next_year",
        "analyst_buy_ratio",
        "analyst_hold_ratio",
        "analyst_buy_ratio_change_3m",
        "target_mean",
        "target_high",
        "target_low",
        "target_median",
        "target_current",
        "target_upside",
        "next_earnings_date",
        "calendar_earnings_average",
        "calendar_revenue_average",
    ]
    equity_metadata = equity_metadata.reindex(columns=metadata_columns)
    merged = fundamentals.merge(price_snapshot, on="ticker", how="left")
    merged = merged.merge(
        equity_metadata.drop_duplicates(subset=["ticker"]),
        on="ticker",
        how="left",
    )
    if analyst_views is not None and not analyst_views.empty:
        overlay = analyst_views.copy()
        overlay["ticker"] = overlay["ticker"].astype(str).str.upper()
        overlay_columns = [
            "ticker",
            "stance",
            "conviction",
            "thesis",
            "catalyst",
            "risk",
            "client_angle",
            "management_access_note",
        ]
        overlay = overlay.reindex(columns=overlay_columns)
        merged = merged.merge(overlay.drop_duplicates(subset=["ticker"]), on="ticker", how="left")

    merged["market_cap"] = merged["close"] * merged["shares_outstanding"]
    if "reported_market_cap" in merged.columns:
        merged["market_cap"] = merged["market_cap"].fillna(merged["reported_market_cap"])
    merged["price_to_sales"] = merged["market_cap"] / merged["revenue"]
    merged["pe_ratio"] = merged["market_cap"] / merged["net_income"]
    if "reported_pe" in merged.columns:
        merged["pe_ratio"] = merged["pe_ratio"].fillna(merged["reported_pe"])
    if "target_upside" in merged.columns:
        merged["target_upside"] = merged["target_upside"].fillna(
            (merged["target_mean"] / merged["close"]) - 1
        )
    merged["forward_eps_growth"] = merged["eps_growth_next_year"].fillna(merged["eps_growth_current_year"])
    merged["next_earnings_date"] = pd.to_datetime(merged["next_earnings_date"], errors="coerce")

    merged.loc[merged["price_to_sales"] <= 0, "price_to_sales"] = pd.NA
    merged.loc[merged["pe_ratio"] <= 0, "pe_ratio"] = pd.NA

    merged["valuation_score"] = (
        _percentile_score(merged["pe_ratio"], higher_is_better=False)
        + _percentile_score(merged["price_to_sales"], higher_is_better=False)
    ) / 2
    merged["growth_score"] = _percentile_score(merged["revenue_growth"], higher_is_better=True)
    merged["quality_score"] = (
        _percentile_score(merged["net_margin"], higher_is_better=True)
        + _percentile_score(merged["roe"], higher_is_better=True)
    ) / 2
    merged["momentum_score"] = (
        _percentile_score(merged["ret_1m"], higher_is_better=True)
        + _percentile_score(merged["ret_3m"], higher_is_better=True)
    ) / 2
    merged["forward_score"] = (
        _percentile_score(merged["forward_eps_growth"], higher_is_better=True)
        + _percentile_score(merged["target_upside"], higher_is_better=True)
        + _percentile_score(merged["analyst_buy_ratio"], higher_is_better=True)
        + _percentile_score(merged["analyst_buy_ratio_change_3m"], higher_is_better=True)
    ) / 4
    merged["composite_score"] = merged[
        ["valuation_score", "growth_score", "quality_score", "momentum_score"]
    ].mean(axis=1, skipna=True)
    stance_map = {
        "overweight": 1.0,
        "buy": 1.0,
        "positive": 0.85,
        "neutral": 0.5,
        "hold": 0.5,
        "underweight": 0.15,
        "sell": 0.0,
        "negative": 0.0,
    }
    merged["stance_score"] = merged.get("stance", pd.Series(dtype="object")).astype(str).str.lower().map(stance_map)
    merged["conviction_score"] = pd.to_numeric(merged.get("conviction"), errors="coerce") / 5
    merged["discretionary_score"] = merged[["stance_score", "conviction_score"]].mean(axis=1, skipna=True)
    merged["research_score"] = merged[
        ["composite_score", "forward_score", "discretionary_score"]
    ].mean(axis=1, skipna=True)
    merged["research_score"] = merged["research_score"].fillna(merged["composite_score"])
    merged["screen_rank"] = merged["research_score"].rank(ascending=False, method="dense")

    merged["as_of_date"] = as_of_date.isoformat()
    merged = merged.sort_values(
        by=["research_score", "target_upside", "ret_1m", "market_cap"],
        ascending=[False, False, False, False],
    )
    return merged.reset_index(drop=True)


def top_screen_candidates(research_dataset: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    if research_dataset.empty:
        return research_dataset
    return research_dataset.head(limit).reset_index(drop=True)


def build_stock_callouts(research_dataset: pd.DataFrame, limit: int = 3) -> list[str]:
    if research_dataset.empty:
        return []

    callouts = []
    for _, row in research_dataset.head(limit).iterrows():
        company_name = (
            row["company_name"]
            if pd.notna(row.get("company_name"))
            else row.get("long_name")
            if pd.notna(row.get("long_name"))
            else row["ticker"]
        )
        sector = row["sector"] if pd.notna(row.get("sector")) else "Unclassified"
        revenue_growth = row["revenue_growth"] if pd.notna(row.get("revenue_growth")) else 0.0
        roe = row["roe"] if pd.notna(row.get("roe")) else 0.0
        forward_eps = row["forward_eps_growth"] if pd.notna(row.get("forward_eps_growth")) else None
        target_upside = row["target_upside"] if pd.notna(row.get("target_upside")) else None
        if forward_eps is not None and target_upside is not None:
            callouts.append(
                (
                    f"{row['ticker']} ({company_name}) screens well inside {sector} with "
                    f"{forward_eps * 100:.1f}% forward EPS growth, "
                    f"{target_upside * 100:.1f}% implied target upside, and "
                    f"{roe * 100:.1f}% ROE."
                )
            )
        else:
            ret_1m = row["ret_1m"] if pd.notna(row.get("ret_1m")) else 0.0
            callouts.append(
                (
                    f"{row['ticker']} ({company_name}) screens well inside {sector} with "
                    f"{revenue_growth * 100:.1f}% revenue growth, "
                    f"{roe * 100:.1f}% ROE, and "
                    f"{ret_1m * 100:.1f}% one-month momentum."
                )
            )
    return callouts
