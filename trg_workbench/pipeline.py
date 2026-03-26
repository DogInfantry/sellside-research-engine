from __future__ import annotations

from calendar import monthrange
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from trg_workbench.analytics.kpis import build_kpi_context
from trg_workbench.analytics.screening import build_research_dataset, build_stock_callouts, top_screen_candidates
from trg_workbench.analytics.summaries import (
    build_catalyst_calendar,
    build_client_angles,
    build_europe_summary,
    build_management_notes,
    build_macro_summary,
    build_sector_summary,
    build_sector_narratives,
    build_tactical_takeaways,
    generate_weekly_theme,
)
from trg_workbench.config import ANALYST_VIEWS_PATH, DEFAULT_US_TICKERS, EUROPE_INDICES, NORMALIZED_DIR, OUTPUTS_DIR, ROOT_DIR, US_SECTOR_PROXIES
from trg_workbench.io_utils import (
    append_jsonl,
    ensure_directories,
    load_dataframe,
    read_json,
    resolve_manifest,
    save_dataframe,
    utc_now_iso,
    write_json,
)
from trg_workbench.reporting.renderers import build_kpi_charts, render_template, write_report
from trg_workbench.sources.ecb import ECBClient
from trg_workbench.sources.market import MarketDataClient
from trg_workbench.sources.sec import SECClient


PIPELINE_LOG_PATH = ROOT_DIR / "data" / "logs" / "pipeline_events.jsonl"


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT_DIR))


def _manifest_dataset_path(manifest: dict[str, Any], dataset_name: str) -> Path:
    return ROOT_DIR / manifest["datasets"][dataset_name]["path"]


def _log_event(event_type: str, **payload: Any) -> None:
    append_jsonl(
        PIPELINE_LOG_PATH,
        {
            "timestamp": utc_now_iso(),
            "event_type": event_type,
            **payload,
        },
    )


def _load_bundle(target_date: date) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest_path = resolve_manifest(target_date)
    manifest = read_json(manifest_path)

    fundamentals = load_dataframe(
        _manifest_dataset_path(manifest, "fundamentals"),
        parse_dates=["period_end", "filing_date"],
    )
    prices = load_dataframe(_manifest_dataset_path(manifest, "prices"), parse_dates=["date"])
    metadata = load_dataframe(_manifest_dataset_path(manifest, "metadata"))
    macro = load_dataframe(_manifest_dataset_path(manifest, "macro"), parse_dates=["date"])
    return manifest, fundamentals, prices, metadata, macro


def _load_analyst_views() -> pd.DataFrame:
    if not ANALYST_VIEWS_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(ANALYST_VIEWS_PATH)


def _build_analyst_overlays(research_dataset: pd.DataFrame, limit: int = 3) -> list[dict[str, object]]:
    if research_dataset.empty or "thesis" not in research_dataset.columns:
        return []
    overlays = research_dataset.dropna(subset=["thesis"]).sort_values("screen_rank").head(limit)
    if overlays.empty:
        return []
    return overlays[
        ["ticker", "stance", "conviction", "thesis", "catalyst", "risk"]
    ].to_dict(orient="records")


def _yahoo_fundamentals_fallback(metadata: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    if metadata.empty:
        return pd.DataFrame()

    equities = metadata.loc[metadata["instrument_group"] == "us_equity"].copy()
    if equities.empty:
        return pd.DataFrame()

    equities["revenue_growth"] = pd.to_numeric(equities["revenue_growth"], errors="coerce")
    equities["profit_margins"] = pd.to_numeric(equities["profit_margins"], errors="coerce")
    equities["return_on_equity"] = pd.to_numeric(equities["return_on_equity"], errors="coerce")
    equities["total_revenue"] = pd.to_numeric(equities["total_revenue"], errors="coerce")
    equities["net_income_to_common"] = pd.to_numeric(equities["net_income_to_common"], errors="coerce")
    equities["shares_outstanding"] = pd.to_numeric(equities["shares_outstanding"], errors="coerce")
    equities["market_cap"] = pd.to_numeric(equities["market_cap"], errors="coerce")
    equities["trailing_pe"] = pd.to_numeric(equities["trailing_pe"], errors="coerce")

    equities["previous_revenue"] = equities.apply(
        lambda row: row["total_revenue"] / (1 + row["revenue_growth"])
        if pd.notna(row["total_revenue"])
        and pd.notna(row["revenue_growth"])
        and row["revenue_growth"] > -0.99
        else pd.NA,
        axis=1,
    )
    equities["equity"] = equities.apply(
        lambda row: row["net_income_to_common"] / row["return_on_equity"]
        if pd.notna(row["net_income_to_common"])
        and pd.notna(row["return_on_equity"])
        and row["return_on_equity"] not in (0, 0.0)
        else pd.NA,
        axis=1,
    )

    fallback = pd.DataFrame(
        {
            "ticker": equities["ticker"],
            "cik": pd.NA,
            "company_name": equities["long_name"],
            "fiscal_year": as_of_date.year,
            "period_end": pd.Timestamp(as_of_date),
            "filing_date": pd.Timestamp(as_of_date),
            "revenue": equities["total_revenue"],
            "previous_revenue": equities["previous_revenue"],
            "revenue_growth": equities["revenue_growth"],
            "net_income": equities["net_income_to_common"],
            "equity": equities["equity"],
            "assets": pd.NA,
            "shares_outstanding": equities["shares_outstanding"],
            "net_margin": equities["profit_margins"],
            "roe": equities["return_on_equity"],
            "reported_market_cap": equities["market_cap"],
            "reported_pe": equities["trailing_pe"],
            "source": "Yahoo Finance fallback",
            "retrieved_at": utc_now_iso(),
            "as_of_date": as_of_date.isoformat(),
        }
    )
    return fallback.dropna(
        subset=["revenue", "net_income", "shares_outstanding", "reported_market_cap"],
        how="all",
    ).reset_index(drop=True)


def fetch_data(as_of_date: date) -> dict[str, Any]:
    ensure_directories()
    start = perf_counter()

    sec_client = SECClient()
    ecb_client = ECBClient()
    market_client = MarketDataClient()

    prices, metadata = market_client.build_market_dataset(as_of_date)
    try:
        fundamentals, sec_issues = sec_client.build_fundamentals(DEFAULT_US_TICKERS, as_of_date)
    except Exception as exc:  # noqa: BLE001
        fundamentals = pd.DataFrame()
        sec_issues = [{"ticker": "ALL", "issue": str(exc)}]
    if fundamentals.empty:
        fundamentals = _yahoo_fundamentals_fallback(metadata, as_of_date)
        sec_issues.append(
            {
                "ticker": "ALL",
                "issue": "SEC fundamentals unavailable; fell back to Yahoo Finance fundamental fields.",
            }
        )

    macro, ecb_issues = ecb_client.build_macro_dataset(as_of_date)

    fundamentals_path = NORMALIZED_DIR / f"sec_fundamentals_{as_of_date.isoformat()}.csv"
    prices_path = NORMALIZED_DIR / f"market_prices_{as_of_date.isoformat()}.csv"
    metadata_path = NORMALIZED_DIR / f"security_master_{as_of_date.isoformat()}.csv"
    macro_path = NORMALIZED_DIR / f"ecb_macro_{as_of_date.isoformat()}.csv"
    manifest_path = NORMALIZED_DIR / f"manifest_{as_of_date.isoformat()}.json"

    save_dataframe(fundamentals, fundamentals_path)
    save_dataframe(prices, prices_path)
    save_dataframe(metadata, metadata_path)
    save_dataframe(macro, macro_path)

    manifest = {
        "as_of_date": as_of_date.isoformat(),
        "generated_at": utc_now_iso(),
        "datasets": {
            "fundamentals": {
                "path": _relative(fundamentals_path),
                "source": (
                    "SEC"
                    if not fundamentals.empty and set(fundamentals["source"].dropna().unique()) == {"SEC"}
                    else "Yahoo Finance fallback"
                ),
                "rows": int(len(fundamentals)),
                "issues": sec_issues,
            },
            "prices": {
                "path": _relative(prices_path),
                "source": "Yahoo Finance",
                "rows": int(len(prices)),
                "issues": [],
            },
            "metadata": {
                "path": _relative(metadata_path),
                "source": "Yahoo Finance",
                "rows": int(len(metadata)),
                "issues": [],
            },
            "macro": {
                "path": _relative(macro_path),
                "source": "ECB",
                "rows": int(len(macro)),
                "issues": ecb_issues,
            },
        },
        "coverage": {
            "us_equities": int(fundamentals["ticker"].nunique()) if not fundamentals.empty else 0,
            "sector_proxies": int(prices.loc[prices["ticker"].isin(US_SECTOR_PROXIES)].ticker.nunique())
            if not prices.empty
            else 0,
            "europe_indices": int(prices.loc[prices["ticker"].isin(EUROPE_INDICES)].ticker.nunique())
            if not prices.empty
            else 0,
            "macro_series": int(macro["label"].nunique()) if not macro.empty else 0,
        },
    }
    write_json(manifest_path, manifest)

    for dataset_name, dataset in manifest["datasets"].items():
        _log_event(
            "fetch_source",
            source=dataset["source"],
            dataset=dataset_name,
            rows=dataset["rows"],
            issues=len(dataset["issues"]),
            as_of_date=as_of_date.isoformat(),
            path=dataset["path"],
        )

    _log_event(
        "fetch_run",
        as_of_date=as_of_date.isoformat(),
        duration_seconds=round(perf_counter() - start, 2),
        coverage=manifest["coverage"],
    )

    print(f"Fetched data for {as_of_date.isoformat()}")
    print(f"- SEC fundamentals rows: {len(fundamentals)}")
    print(f"- Market price rows: {len(prices)}")
    print(f"- ECB macro rows: {len(macro)}")
    return manifest


def build_daily_report(report_date: date) -> Path:
    ensure_directories()
    manifest, fundamentals, prices, metadata, macro = _load_bundle(report_date)
    analyst_views = _load_analyst_views()
    research_dataset = build_research_dataset(
        fundamentals,
        prices,
        metadata,
        report_date,
        analyst_views=analyst_views,
    )
    sector_summary = build_sector_summary(prices, report_date)
    europe_summary = build_europe_summary(prices, report_date)
    macro_summary = build_macro_summary(macro, report_date)
    sector_narratives = build_sector_narratives(research_dataset)
    catalyst_calendar = build_catalyst_calendar(research_dataset, report_date)
    analyst_overlays = _build_analyst_overlays(research_dataset)
    takeaways = build_tactical_takeaways(
        research_dataset=research_dataset,
        sector_summary=sector_summary,
        europe_summary=europe_summary,
        macro_summary=macro_summary,
    )

    output_path = OUTPUTS_DIR / f"daily_note_{report_date.isoformat()}.md"
    content = render_template(
        "daily_note.md.j2",
        {
            "report_date": report_date.isoformat(),
            "data_as_of": manifest["as_of_date"],
            "macro_summary": macro_summary.to_dict(orient="records"),
            "sector_summary": sector_summary.head(8).to_dict(orient="records"),
            "europe_summary": europe_summary.to_dict(orient="records"),
            "top_candidates": top_screen_candidates(research_dataset, limit=8).to_dict(orient="records"),
            "sector_narratives": sector_narratives,
            "catalyst_calendar": catalyst_calendar,
            "analyst_overlays": analyst_overlays,
            "takeaways": takeaways,
        },
    )
    write_report(output_path, content)

    _log_event(
        "report_generated",
        report_type="daily",
        as_of_date=manifest["as_of_date"],
        requested_date=report_date.isoformat(),
        path=_relative(output_path),
        rows=int(len(research_dataset)),
    )
    print(f"Wrote daily note to {output_path}")
    return output_path


def build_weekly_report(report_date: date) -> Path:
    ensure_directories()
    manifest, fundamentals, prices, metadata, macro = _load_bundle(report_date)
    analyst_views = _load_analyst_views()
    research_dataset = build_research_dataset(
        fundamentals,
        prices,
        metadata,
        report_date,
        analyst_views=analyst_views,
    )
    europe_summary = build_europe_summary(prices, report_date)
    sector_summary = build_sector_summary(prices, report_date)
    macro_summary = build_macro_summary(macro, report_date)
    sector_narratives = build_sector_narratives(research_dataset)
    weekly_theme = generate_weekly_theme(
        research_dataset=research_dataset,
        sector_summary=sector_summary,
        europe_summary=europe_summary,
        macro_summary=macro_summary,
    )
    stock_callouts = build_stock_callouts(research_dataset, limit=3)
    catalyst_calendar = build_catalyst_calendar(research_dataset, report_date)
    client_angles = build_client_angles(research_dataset)
    management_notes = build_management_notes(research_dataset)
    analyst_overlays = _build_analyst_overlays(research_dataset)

    output_path = OUTPUTS_DIR / f"weekly_wrap_{report_date.isoformat()}.md"
    content = render_template(
        "weekly_wrap.md.j2",
        {
            "report_date": report_date.isoformat(),
            "data_as_of": manifest["as_of_date"],
            "weekly_theme": weekly_theme,
            "top_candidates": top_screen_candidates(research_dataset, limit=10).to_dict(orient="records"),
            "stock_callouts": stock_callouts,
            "europe_summary": europe_summary.to_dict(orient="records"),
            "sector_narratives": sector_narratives,
            "catalyst_calendar": catalyst_calendar,
            "client_angles": client_angles,
            "management_notes": management_notes,
            "analyst_overlays": analyst_overlays,
        },
    )
    write_report(output_path, content)

    _log_event(
        "report_generated",
        report_type="weekly",
        as_of_date=manifest["as_of_date"],
        requested_date=report_date.isoformat(),
        path=_relative(output_path),
        rows=int(len(research_dataset)),
    )
    print(f"Wrote weekly wrap to {output_path}")
    return output_path


def build_kpi_report(month: str) -> Path:
    ensure_directories()
    context = build_kpi_context(month, NORMALIZED_DIR)
    charts = build_kpi_charts(context)

    output_path = OUTPUTS_DIR / f"kpi_report_{month}.html"
    content = render_template(
        "kpi_report.html.j2",
        {
            "summary": context["summary"],
            "charts": charts,
            "source_freshness": context["source_freshness"].assign(
                last_timestamp=lambda frame: frame["last_timestamp"].astype(str)
            ).to_dict(orient="records")
            if not context["source_freshness"].empty
            else [],
        },
    )
    write_report(output_path, content)

    year, month_number = month.split("-")
    last_day = monthrange(int(year), int(month_number))[1]
    _log_event(
        "report_generated",
        report_type="kpi",
        as_of_date=f"{month}-{last_day:02d}",
        requested_date=month,
        path=_relative(output_path),
        rows=int(context["summary"]["report_count"]),
    )
    print(f"Wrote KPI report to {output_path}")
    return output_path


def build_all(as_of_date: date) -> list[Path]:
    fetch_data(as_of_date)
    outputs = [
        build_daily_report(as_of_date),
        build_weekly_report(as_of_date),
        build_kpi_report(as_of_date.strftime("%Y-%m")),
    ]
    return outputs
