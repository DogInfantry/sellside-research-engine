from __future__ import annotations

from datetime import date

import pandas as pd

from trg_workbench.analytics.screening import build_price_snapshot
from trg_workbench.config import EUROPE_INDICES, US_SECTOR_PROXIES
from trg_workbench.utils import pct


def build_sector_summary(prices: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    snapshot = build_price_snapshot(prices, as_of_date)
    if snapshot.empty:
        return snapshot
    sector_frame = snapshot.loc[snapshot["ticker"].isin(US_SECTOR_PROXIES)].copy()
    sector_frame["display_name"] = sector_frame["ticker"].map(US_SECTOR_PROXIES)
    return sector_frame.sort_values("ret_1w", ascending=False).reset_index(drop=True)


def build_europe_summary(prices: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    snapshot = build_price_snapshot(prices, as_of_date)
    if snapshot.empty:
        return snapshot
    europe_frame = snapshot.loc[snapshot["ticker"].isin(EUROPE_INDICES)].copy()
    europe_frame["display_name"] = europe_frame["ticker"].map(EUROPE_INDICES)
    return europe_frame.sort_values("ret_1w", ascending=False).reset_index(drop=True)


def build_macro_summary(macro: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    if macro.empty:
        return pd.DataFrame()
    subset = macro.loc[pd.to_datetime(macro["date"]).dt.date <= as_of_date].copy()
    if subset.empty:
        return pd.DataFrame()
    subset["date"] = pd.to_datetime(subset["date"])

    rows = []
    for label, group in subset.groupby("label"):
        ordered = group.sort_values("date")
        latest = ordered.iloc[-1]
        prior = ordered.iloc[-6] if len(ordered) > 5 else ordered.iloc[0]
        rows.append(
            {
                "label": label,
                "display_name": latest["display_name"],
                "category": latest["category"],
                "latest_value": latest["value"],
                "one_week_change": latest["value"] - prior["value"],
                "last_updated": latest["date"],
            }
        )
    frame = pd.DataFrame(rows)
    category_order = {"rates": 0, "fx": 1}
    frame["category_order"] = frame["category"].map(category_order).fillna(99)
    frame = frame.sort_values(["category_order", "display_name"]).drop(columns="category_order")
    return frame.reset_index(drop=True)


def build_tactical_takeaways(
    research_dataset: pd.DataFrame,
    sector_summary: pd.DataFrame,
    europe_summary: pd.DataFrame,
    macro_summary: pd.DataFrame,
) -> list[str]:
    takeaways: list[str] = []
    if not sector_summary.empty:
        leader = sector_summary.iloc[0]
        takeaways.append(
            f"US sector leadership sits with {leader['display_name']}, up {pct(leader['ret_1w'])} over the last week."
        )

    if not research_dataset.empty:
        top_name = research_dataset.iloc[0]
        takeaways.append(
            f"The highest-ranked screen name is {top_name['ticker']}, pairing {pct(top_name.get('forward_eps_growth'))} forward EPS growth with {pct(top_name.get('target_upside'))} implied upside."
        )

    if not europe_summary.empty:
        leader = europe_summary.iloc[0]
        takeaways.append(
            f"Europe remains constructive on the tape, led by {leader['display_name']} at {pct(leader['ret_1w'])} week-over-week."
        )

    rate_frame = macro_summary.loc[macro_summary["category"] == "rates"] if not macro_summary.empty else pd.DataFrame()
    if not rate_frame.empty and len(takeaways) < 3:
        rate_row = rate_frame.iloc[0]
        takeaways.append(
            f"ECB policy tone is stable: {rate_row['display_name']} moved {rate_row['one_week_change']:.2f} percentage points over the last week."
        )

    return takeaways[:3]


def build_sector_narratives(research_dataset: pd.DataFrame, limit: int = 3) -> list[str]:
    if research_dataset.empty or "sector" not in research_dataset.columns:
        return []

    sector_frame = research_dataset.dropna(subset=["sector"]).copy()
    if sector_frame.empty:
        return []

    grouped = (
        sector_frame.groupby("sector")
        .agg(
            avg_research_score=("research_score", "mean"),
            avg_target_upside=("target_upside", "mean"),
            avg_buy_ratio=("analyst_buy_ratio", "mean"),
            avg_ret_1m=("ret_1m", "mean"),
            names=("ticker", "count"),
        )
        .sort_values("avg_research_score", ascending=False)
        .reset_index()
    )

    narratives: list[str] = []
    for _, row in grouped.head(limit).iterrows():
        upside_text = (
            "with meaningful target upside"
            if pd.notna(row["avg_target_upside"]) and row["avg_target_upside"] > 0.10
            else "with a more modest upside profile"
        )
        sentiment_text = (
            "buy-side sentiment remains supportive"
            if pd.notna(row["avg_buy_ratio"]) and row["avg_buy_ratio"] >= 0.65
            else "consensus positioning is more balanced"
        )
        momentum_text = (
            "after a strong near-term run"
            if pd.notna(row["avg_ret_1m"]) and row["avg_ret_1m"] >= 0.08
            else "without especially stretched momentum"
        )
        narratives.append(
            f"{row['sector']} screens well on the current cut, {upside_text}; {sentiment_text}, and the group is trading {momentum_text}."
        )
    return narratives


def build_catalyst_calendar(research_dataset: pd.DataFrame, as_of_date: date, limit: int = 5) -> list[dict[str, object]]:
    if research_dataset.empty or "next_earnings_date" not in research_dataset.columns:
        return []
    frame = research_dataset.copy()
    frame["next_earnings_date"] = pd.to_datetime(frame["next_earnings_date"], errors="coerce")
    frame = frame.loc[frame["next_earnings_date"].notna()].copy()
    frame = frame.loc[frame["next_earnings_date"].dt.date >= as_of_date]
    if frame.empty:
        return []
    frame = frame.sort_values(["next_earnings_date", "screen_rank"]).head(limit)
    return frame[
        ["ticker", "company_name", "next_earnings_date", "calendar_earnings_average", "calendar_revenue_average"]
    ].to_dict(orient="records")


def build_client_angles(research_dataset: pd.DataFrame, limit: int = 3) -> list[str]:
    if research_dataset.empty:
        return []

    explicit = research_dataset.dropna(subset=["client_angle"]) if "client_angle" in research_dataset.columns else pd.DataFrame()
    if not explicit.empty:
        rows = explicit.sort_values("screen_rank").head(limit)
        return [f"{row['ticker']}: {row['client_angle']}" for _, row in rows.iterrows()]

    rows = research_dataset.head(limit)
    angles = []
    for _, row in rows.iterrows():
        company = row["company_name"] if pd.notna(row.get("company_name")) else row["ticker"]
        angles.append(
            f"{row['ticker']} ({company}) is a client-friendly discussion point because it combines {pct(row.get('target_upside'))} target upside with {pct(row.get('forward_eps_growth'))} forward EPS growth."
        )
    return angles


def build_management_notes(research_dataset: pd.DataFrame, limit: int = 3) -> list[str]:
    if research_dataset.empty or "management_access_note" not in research_dataset.columns:
        return []
    notes = research_dataset.dropna(subset=["management_access_note"]).sort_values("screen_rank").head(limit)
    return [f"{row['ticker']}: {row['management_access_note']}" for _, row in notes.iterrows()]


def generate_weekly_theme(
    research_dataset: pd.DataFrame,
    sector_summary: pd.DataFrame,
    europe_summary: pd.DataFrame,
    macro_summary: pd.DataFrame,
) -> dict[str, str]:
    breadth = None
    if not sector_summary.empty:
        breadth = float((sector_summary["ret_1w"] > 0).mean())

    if breadth is not None and breadth >= 0.7 and not research_dataset.empty:
        top_name = research_dataset.iloc[0]["ticker"]
        return {
            "title": "Broadening risk appetite supports bottom-up stock selection",
            "body": (
                f"{breadth:.0%} of US sector proxies were positive on a one-week basis, "
                f"while the screen continues to favor names such as {top_name} with both valuation support and positive momentum."
            ),
        }

    fx_frame = macro_summary.loc[macro_summary["category"] == "fx"] if not macro_summary.empty else pd.DataFrame()
    if not fx_frame.empty:
        fx_row = fx_frame.iloc[0]
        return {
            "title": "FX remains a key swing factor in the Europe overlay",
            "body": (
                f"{fx_row['display_name']} moved by {fx_row['one_week_change']:.3f} over the last week, "
                "keeping currency translation and regional market dispersion high on the thematic agenda."
            ),
        }

    if not europe_summary.empty:
        europe_row = europe_summary.iloc[0]
        return {
            "title": "Europe index leadership is driving the global overlay",
            "body": (
                f"{europe_row['display_name']} led the monitored Europe indices with a {pct(europe_row['ret_1w'])} weekly gain."
            ),
        }

    return {
        "title": "Research focus stays on fundamental resilience",
        "body": "With limited macro dispersion in the current pull, the screen leans on profitability and stable growth rather than top-down rotation alone.",
    }
