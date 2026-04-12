"""
pipeline_v2.py — Enhanced orchestration pipeline for TRG Research Workbench v2.

New in v2:
  - US macro data (Fed rates, UST yields, VIX, DXY, Gold, WTI via yfinance)
  - Risk analytics (VaR, CVaR, beta, Sharpe, Sortino, max drawdown)
  - Valuation analytics (DCF, sensitivity, football field, scenarios)
  - 12 chart types generating PNGs (sector heatmap, risk-return, correlation, radar, etc.)
  - Professional HTML research note (GS-style, chart-embedded, printable to PDF)
  - PDF output via WeasyPrint (falls back to HTML if not installed)
  - Enhanced Markdown note (unchanged for compatibility)
"""
from __future__ import annotations

import logging
from datetime import datetime, date as _date_type
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys
from tqdm import tqdm



import pandas as pd

from trg_workbench.config import (
    CHARTS_DIR,
    DATA_DIR,
    NORMALIZED_DIR,
    OUTPUTS_DIR,
    US_SECTOR_PROXIES,
)
from trg_workbench.io_utils import (
    append_jsonl,
    ensure_directories,
    load_dataframe,
    resolve_manifest,
    save_dataframe,
    utc_now_iso,
    write_json,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ─── helpers ──────────────────────────────────────────────────────────────────

def _log(event_type: str, payload: Dict, as_of: str) -> None:
    append_jsonl(
        DATA_DIR / "logs" / "pipeline_events.jsonl",
        {"event": event_type, "as_of": as_of, "ts": utc_now_iso(), **payload},
    )


def _load_prices(as_of: str) -> pd.DataFrame:
    """Load normalized market prices in LONG format (date, ticker, Close, Volume).
    This is the format expected by v1 analytics (screening.py)."""
    path = NORMALIZED_DIR / f"market_prices_{as_of}.csv"
    if not path.exists():
        logger.warning("Prices file not found: %s", path)
        return pd.DataFrame()
    return load_dataframe(path, parse_dates=["date"])


def _prices_wide(prices_long: pd.DataFrame) -> pd.DataFrame:
    """Pivot long-format prices to wide format (date index, ticker columns, Close values).
    Used by v2 risk analytics and chart generators."""
    if prices_long.empty:
        return pd.DataFrame()
    # Support both 'Close' and 'close' column names
    close_col = "Close" if "Close" in prices_long.columns else "close" if "close" in prices_long.columns else None
    if "ticker" not in prices_long.columns or close_col is None:
        return pd.DataFrame()
    wide = prices_long.pivot_table(index="date", columns="ticker", values=close_col)
    wide.index = pd.to_datetime(wide.index)
    wide = wide.sort_index()
    return wide


def _load_fundamentals(as_of: str) -> pd.DataFrame:
    path = NORMALIZED_DIR / f"sec_fundamentals_{as_of}.csv"
    if not path.exists():
        return pd.DataFrame()
    return load_dataframe(path)


def _load_security_master(as_of: str) -> pd.DataFrame:
    path = NORMALIZED_DIR / f"security_master_{as_of}.csv"
    if not path.exists():
        return pd.DataFrame()
    return load_dataframe(path)


def _load_ecb(as_of: str) -> pd.DataFrame:
    path = NORMALIZED_DIR / f"ecb_macro_{as_of}.csv"
    if not path.exists():
        return pd.DataFrame()
    return load_dataframe(path)


# ─── v2 fetch ────────────────────────────────────────────────────────────────

def fetch_data_v2(as_of: str) -> Dict[str, Any]:
    """
    Fetch all data sources including new US macro.
    Calls original fetch_data() then adds US macro layer.
    """
    from datetime import date as _date
    from trg_workbench.pipeline import fetch_data as fetch_data_v1
    from trg_workbench.sources.macro_us import USMacroClient

    # v1 pipeline expects a date object, not a string
    as_of_date_obj = _date.fromisoformat(as_of) if isinstance(as_of, str) else as_of

    # Run v1 data fetch (market, SEC, ECB)
    logger.info("Running v1 data fetch (market, SEC, ECB)...")
    v1_result = fetch_data_v1(as_of_date_obj)

    # Fetch US macro
    logger.info("Fetching US macro data...")
    macro_client = USMacroClient(cache_dir=DATA_DIR / "cache")
    try:
        macro_snapshot = macro_client.build_snapshot(as_of_date=as_of)
        yield_curve = macro_client.yield_curve_spread(as_of_date=as_of)
        macro_regime = macro_client.macro_regime(macro_snapshot)

        # Save to normalized
        save_dataframe(macro_snapshot, NORMALIZED_DIR / f"us_macro_{as_of}.csv")
        _log("fetch_source", {"source": "us_macro", "rows": len(macro_snapshot)}, as_of)
        logger.info("US macro: %d series fetched.", len(macro_snapshot))
    except Exception as exc:  # noqa: BLE001
        logger.warning("US macro fetch failed: %s", exc)
        macro_snapshot = pd.DataFrame()
        yield_curve = {}
        macro_regime = "Unknown"

    return {
        **v1_result,
        "us_macro_snapshot": macro_snapshot,
        "yield_curve": yield_curve,
        "macro_regime": macro_regime,
    }


# ─── v2 report builder ────────────────────────────────────────────────────────

def build_research_report_v2(
    as_of: str,
    output_formats: Optional[List[str]] = None,
    quiet: bool = False,
) -> Dict[str, Path]:
    """
    Build a full research report with all v2 enhancements.
    """
    # 1. Master Switch for TTY and Quiet Mode
    disable_prog = quiet or not sys.stdout.isatty()

    if output_formats is None:
        output_formats = ["html", "pdf", "markdown"]

    ensure_directories()
    outputs: Dict[str, Path] = {}

    # Normalize dates
    as_of_str: str = as_of if isinstance(as_of, str) else as_of.isoformat()
    as_of_date: _date_type = _date_type.fromisoformat(as_of_str) if isinstance(as_of, str) else as_of
    as_of = as_of_str 

    # ── 1. Load data bundle ──────────────────────────────────────────────────
    logger.info("Loading data bundle for %s...", as_of)
    prices_df = _load_prices(as_of)
    fundamentals_df = _load_fundamentals(as_of)
    security_master_df = _load_security_master(as_of)
    ecb_df = _load_ecb(as_of)

    # US macro loading
    us_macro_path = NORMALIZED_DIR / f"us_macro_{as_of}.csv"
    if us_macro_path.exists():
        us_macro_df = load_dataframe(us_macro_path)
    else:
        from trg_workbench.sources.macro_us import USMacroClient
        macro_client = USMacroClient(cache_dir=DATA_DIR / "cache")
        us_macro_df = macro_client.build_snapshot(as_of_date=as_of)

    if prices_df.empty:
        logger.error("No price data available for %s — run fetch-data first.", as_of)
        return {}

    prices_wide = _prices_wide(prices_df)

    # ── 2. Analytics ─────────────────────────────────────────────────────────
    from trg_workbench.analytics.screening import (
        build_price_snapshot, build_research_dataset, build_stock_callouts, top_screen_candidates
    )
    from trg_workbench.analytics.summaries import (
        build_catalyst_calendar, build_europe_summary, build_macro_summary, 
        build_sector_summary, build_tactical_takeaways
    )

    research_df = build_research_dataset(fundamentals_df, prices_df, security_master_df, as_of_date)
    top_candidates = top_screen_candidates(research_df, limit=10)
    callouts = build_stock_callouts(research_df)
    catalyst_rows = build_catalyst_calendar(research_df, as_of_date)

    sector_tickers = list(US_SECTOR_PROXIES.keys())
    sector_summary = build_sector_summary(prices_df, as_of_date)
    europe_summary = build_europe_summary(prices_df, as_of_date)
    macro_summary  = build_macro_summary(ecb_df, as_of_date)
    tactical = build_tactical_takeaways(research_df, sector_summary, europe_summary, macro_summary)

    sector_snap = build_price_snapshot(prices_df, as_of_date)
    sector_snap = sector_snap[sector_snap.index.isin(sector_tickers)].copy()
    sector_snap["sector_name"] = sector_snap.index.map(US_SECTOR_PROXIES)

    # Risk analytics loading
    logger.info("Loading risk metrics...")
    risk_table = pd.DataFrame()
    risk_csv = NORMALIZED_DIR / f"risk_metrics_{as_of}.csv"
    if risk_csv.exists():
        risk_table = pd.read_csv(risk_csv).set_index("ticker")

    # 2c. Valuation analytics for top 3 names
    logger.info("Running valuation analytics...")
    dcf_results = []
    from trg_workbench.analytics.valuation import (
        derive_dcf_inputs,
        dcf_sensitivity,
        football_field,
        reverse_dcf,
        scenario_analysis,
    )

    _tc = "ticker" if "ticker" in top_candidates.columns else None
    top3 = list(top_candidates.head(3)[_tc].values) if (not top_candidates.empty and _tc) else []
    
    for ticker in tqdm(top3, desc="Computing valuations", disable=disable_prog):
        try:
            sm_row = security_master_df[security_master_df["ticker"] == ticker].iloc[0].to_dict() if ticker in security_master_df["ticker"].values else {}
            sec_row = fundamentals_df[fundamentals_df["ticker"] == ticker].iloc[0].to_dict() if ticker in fundamentals_df["ticker"].values else {}
            
            inputs = derive_dcf_inputs(sm_row, sec_row)
            if inputs["base_fcf"] == 0:
                continue

            scenarios = scenario_analysis(inputs["base_fcf"], inputs["base_growth"], inputs["wacc"], inputs["net_debt"], inputs["shares_outstanding"])
            sensitivity_df = dcf_sensitivity(inputs["base_fcf"], [inputs["base_growth"] * (0.85 ** i) for i in range(5)], inputs["net_debt"], inputs["shares_outstanding"])
            current_price = float(prices_wide[ticker].dropna().iloc[-1]) if ticker in prices_wide.columns else 0

            ff = football_field(ticker=ticker, current_price=current_price, 
                                dcf_base=scenarios["Base Case"]["intrinsic_value_per_share"],
                                dcf_bull=scenarios["Bull Case"]["intrinsic_value_per_share"],
                                dcf_bear=scenarios["Bear Case"]["intrinsic_value_per_share"])

            reverse_dcf_result = None
            if current_price > 0:
                try:
                    reverse_dcf_result = reverse_dcf(
                        current_price=current_price,
                        shares_outstanding=inputs["shares_outstanding"],
                        net_debt=inputs["net_debt"],
                        base_fcf=inputs["base_fcf"],
                        wacc=inputs["wacc"],
                        terminal_growth=scenarios["Base Case"]["tgr_used"],
                    )
                except ValueError as exc:
                    logger.warning("Reverse DCF failed for %s: %s", ticker, exc)

            dcf_results.append(
                {
                    "ticker": ticker,
                    "inputs": inputs,
                    "scenarios": scenarios,
                    "sensitivity_df": sensitivity_df,
                    "football_field": ff,
                    "current_price": current_price,
                    "reverse_dcf": reverse_dcf_result,
                }
            )
            
            if disable_prog:
                logger.info("Valuation complete for %s (Base: $%.2f)", ticker, scenarios["Base Case"]["intrinsic_value_per_share"])
        except Exception as exc:
            logger.warning("Valuation failed for %s: %s", ticker, exc)

    # ── 3. Generate charts (Target 2 Integration) ──────────────────────────
    logger.info("Generating research charts...")
    from trg_workbench.reporting.charts import build_research_charts
    
    # We pass the baton (quiet flag) to the chart module
    charts_dict = build_research_charts(
        prices_df=prices_wide,
        research_df=research_df,
        risk_table=risk_table,
        sector_returns=sector_snap,
        macro_snapshot=us_macro_df,
        charts_dir=CHARTS_DIR,
        as_of_date=as_of,
        top_tickers=top3,
        quiet=quiet
    )
    charts = {k: str(v) for k, v in charts_dict.items()}

    # ── 4. Build template context ─────────────────────────────────────────────
    logger.info("Building report context...")
    
    # Sector rows with total=len(df) for percentage accuracy
    sector_rows = []
    for ticker, r in tqdm(sector_snap.iterrows(), desc="Fetching Sector Rows", total=len(sector_snap), disable=disable_prog):
        sector_rows.append({
            "ticker": ticker,
            "sector_name": r.get("sector_name", ticker),
            "ret_1w": float(r.get("ret_1w", 0) or 0),
        })

    # Risk rows with total=len(df)
    risk_rows = []
    if not risk_table.empty:
        for ticker, r in tqdm(risk_table.iterrows(), desc="Fetching Risk Rows", total=len(risk_table), disable=disable_prog):
            d = r.to_dict()
            d["ticker"] = ticker
            risk_rows.append(d)

    context = {
        "report_title": f"TRG Research Note — {as_of}",
        "as_of_date": as_of,
        "sector_rows": sector_rows,
        "risk_rows": risk_rows,
        "dcf_results": dcf_results,
        "charts": charts,
        # ... (rest of context items)
    }

    # ── 5. Render outputs ─────────────────────────────────────────────────────
    from trg_workbench.reporting.pdf_renderer import render_html_only, render_research_note_pdf
    
    html_path = OUTPUTS_DIR / f"research_note_{as_of}.html"
    outputs["html"] = render_html_only(context, html_path)

    if "pdf" in output_formats:
        pdf_path = OUTPUTS_DIR / f"research_note_{as_of}.pdf"
        outputs["pdf"] = render_research_note_pdf(context, pdf_path, quiet=quiet)

    if "markdown" in output_formats:
        from trg_workbench.reporting.renderers import render_template, write_report

        md_path = OUTPUTS_DIR / f"daily_note_{as_of}.md"
        markdown = render_template("daily_note.md.j2", context)
        outputs["markdown"] = write_report(md_path, markdown)

    return outputs
