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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """Load normalized market prices. Returns empty DataFrame on missing file."""
    path = NORMALIZED_DIR / f"market_prices_{as_of}.csv"
    if not path.exists():
        logger.warning("Prices file not found: %s", path)
        return pd.DataFrame()
    df = load_dataframe(path)
    if "Date" in df.columns:
        df = df.set_index("Date")
    df.index = pd.to_datetime(df.index)
    return df


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
    from trg_workbench.pipeline import fetch_data as fetch_data_v1
    from trg_workbench.sources.macro_us import USMacroClient

    # Run v1 data fetch (market, SEC, ECB)
    logger.info("Running v1 data fetch (market, SEC, ECB)...")
    v1_result = fetch_data_v1(as_of)

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
) -> Dict[str, Path]:
    """
    Build a full research report with all v2 enhancements.

    Args:
        as_of: Date string YYYY-MM-DD.
        output_formats: List of formats to generate.
            Options: "html", "pdf", "markdown" (default: all three).

    Returns:
        Dict mapping format name to output file path.
    """
    if output_formats is None:
        output_formats = ["html", "pdf", "markdown"]

    ensure_directories()
    outputs: Dict[str, Path] = {}

    # ── 1. Load data bundle ──────────────────────────────────────────────────
    logger.info("Loading data bundle for %s...", as_of)
    prices_df = _load_prices(as_of)
    fundamentals_df = _load_fundamentals(as_of)
    security_master_df = _load_security_master(as_of)
    ecb_df = _load_ecb(as_of)

    # US macro
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

    # ── 2. Analytics ─────────────────────────────────────────────────────────

    # 2a. Existing screening
    from trg_workbench.analytics.screening import (
        build_price_snapshot,
        build_research_dataset,
        build_stock_callouts,
        top_screen_candidates,
    )
    from trg_workbench.analytics.summaries import (
        build_catalyst_calendar,
        build_macro_summary,
        build_sector_summary,
        build_tactical_takeaways,
    )

    price_snap = build_price_snapshot(prices_df, as_of)

    # Sector snapshot
    sector_tickers = list(US_SECTOR_PROXIES.keys())
    sector_snap = price_snap[price_snap.index.isin(sector_tickers)].copy()
    sector_snap["sector_name"] = sector_snap.index.map(US_SECTOR_PROXIES)

    # Research dataset
    research_df = build_research_dataset(
        price_snap, fundamentals_df, security_master_df, as_of
    )
    top_candidates = top_screen_candidates(research_df, n=10)
    callouts = build_stock_callouts(research_df)
    catalyst_rows = build_catalyst_calendar(security_master_df)
    tactical = build_tactical_takeaways(research_df, sector_snap, ecb_df)

    # 2b. NEW: Risk analytics
    logger.info("Computing risk metrics...")
    risk_table = pd.DataFrame()
    try:
        from trg_workbench.analytics.risk import build_risk_table
        # Use SPY as market proxy if available, else first sector ETF
        all_price_cols = list(prices_df.columns)
        spy_available = "SPY" in all_price_cols
        market_col = "SPY" if spy_available else (sector_tickers[0] if sector_tickers else None)

        # Add SPY if not in universe
        if not spy_available and market_col:
            pass  # use XLK or first available ETF

        risk_table = build_risk_table(
            prices_df,
            market_col=market_col or "XLK",
            rfr=0.053,
        )
        save_dataframe(risk_table.reset_index(), NORMALIZED_DIR / f"risk_metrics_{as_of}.csv")
        logger.info("Risk metrics computed for %d tickers.", len(risk_table))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Risk analytics failed: %s", exc)

    # 2c. NEW: Valuation analytics for top 3 names
    logger.info("Running valuation analytics...")
    dcf_results = []
    try:
        from trg_workbench.analytics.valuation import (
            derive_dcf_inputs,
            dcf_sensitivity,
            football_field,
            scenario_analysis,
        )

        top3 = list(top_candidates.index[:3]) if not top_candidates.empty else []
        for ticker in top3:
            try:
                # Get metadata for this ticker
                sm_row = {}
                if not security_master_df.empty and "ticker" in security_master_df.columns:
                    row = security_master_df[security_master_df["ticker"] == ticker]
                    if not row.empty:
                        sm_row = row.iloc[0].to_dict()

                sec_row = {}
                if not fundamentals_df.empty and "ticker" in fundamentals_df.columns:
                    row = fundamentals_df[fundamentals_df["ticker"] == ticker]
                    if not row.empty:
                        sec_row = row.iloc[0].to_dict()

                inputs = derive_dcf_inputs(sm_row, sec_row)
                if inputs["base_fcf"] == 0:
                    continue

                scenarios = scenario_analysis(
                    inputs["base_fcf"],
                    inputs["base_growth"],
                    inputs["wacc"],
                    inputs["net_debt"],
                    inputs["shares_outstanding"],
                )

                sensitivity_df = dcf_sensitivity(
                    inputs["base_fcf"],
                    [inputs["base_growth"] * (0.85 ** i) for i in range(5)],
                    inputs["net_debt"],
                    inputs["shares_outstanding"],
                )

                current_price = float(prices_df[ticker].dropna().iloc[-1]) if ticker in prices_df.columns else 0

                # Analyst consensus target
                pt_mean = sm_row.get("target_mean_price") or sm_row.get("price_target_mean", 0) or 0
                pt_low = sm_row.get("target_low_price") or 0
                pt_high = sm_row.get("target_high_price") or 0

                ff = football_field(
                    ticker=ticker,
                    current_price=current_price,
                    dcf_base=scenarios["Base Case"]["intrinsic_value_per_share"],
                    dcf_bull=scenarios["Bull Case"]["intrinsic_value_per_share"],
                    dcf_bear=scenarios["Bear Case"]["intrinsic_value_per_share"],
                    analyst_consensus_low=pt_low or None,
                    analyst_consensus_mean=pt_mean or None,
                    analyst_consensus_high=pt_high or None,
                )

                dcf_results.append({
                    "ticker": ticker,
                    "inputs": inputs,
                    "scenarios": scenarios,
                    "sensitivity_df": sensitivity_df,
                    "football_field": ff,
                    "current_price": current_price,
                })
                logger.info("Valuation complete for %s (Base: $%.2f)", ticker,
                            scenarios["Base Case"]["intrinsic_value_per_share"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Valuation failed for %s: %s", ticker, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Valuation module failed: %s", exc)

    # ── 3. Generate charts ────────────────────────────────────────────────────
    logger.info("Generating charts...")
    charts: Dict[str, Path] = {}
    try:
        from trg_workbench.reporting.charts import (
            build_research_charts,
            plot_dcf_sensitivity,
            plot_football_field,
        )

        top_tickers = list(top_candidates.index[:3]) if not top_candidates.empty else []
        charts = build_research_charts(
            prices_df=prices_df,
            research_df=research_df if not research_df.empty else pd.DataFrame(),
            risk_table=risk_table,
            sector_returns=sector_snap,
            macro_snapshot=us_macro_df,
            charts_dir=CHARTS_DIR,
            as_of_date=as_of,
            top_tickers=top_tickers,
        )

        # DCF charts
        tag = as_of.replace("-", "_")
        for dcf in dcf_results:
            ticker = dcf["ticker"]
            current_price = dcf["current_price"]

            # Sensitivity heatmap
            sens_path = CHARTS_DIR / f"dcf_sensitivity_{ticker}_{tag}.png"
            try:
                plot_dcf_sensitivity(dcf["sensitivity_df"], ticker, current_price, sens_path)
                charts[f"dcf_sensitivity_{ticker}"] = sens_path
            except Exception as exc:  # noqa: BLE001
                logger.warning("DCF sensitivity chart failed %s: %s", ticker, exc)

            # Football field
            ff_path = CHARTS_DIR / f"football_{ticker}_{tag}.png"
            try:
                plot_football_field(dcf["football_field"], ff_path)
                charts[f"football_{ticker}"] = ff_path
            except Exception as exc:  # noqa: BLE001
                logger.warning("Football field chart failed %s: %s", ticker, exc)

        logger.info("Charts generated: %d files.", len(charts))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chart generation failed: %s", exc)

    # ── 4. Build template context ─────────────────────────────────────────────
    logger.info("Building report context...")

    # Macro regime
    macro_regime_str = "Unknown"
    vix_level = None
    yield_curve_data = {}
    yield_curve_shape = None
    try:
        from trg_workbench.sources.macro_us import USMacroClient
        mc = USMacroClient(cache_dir=DATA_DIR / "cache")
        yield_curve_data = mc.yield_curve_spread(as_of_date=as_of)
        yield_curve_shape = yield_curve_data.get("curve_shape", "Unknown")
        macro_regime_str = mc.macro_regime(us_macro_df)
        if not us_macro_df.empty:
            vix_row = us_macro_df[us_macro_df["key"] == "vix"] if "key" in us_macro_df.columns else pd.DataFrame()
            if not vix_row.empty:
                vix_level = float(vix_row["value"].iloc[0])
    except Exception:  # noqa: BLE001
        pass

    # US macro rows for table
    us_macro_rows = []
    if not us_macro_df.empty:
        for _, r in us_macro_df.iterrows():
            val = float(r.get("value", 0))
            unit = r.get("unit", "")
            us_macro_rows.append({
                **r.to_dict(),
                "value_fmt": f"{val:.2f}%" if unit == "pct" else f"{val:.2f}",
                "chg_1d": float(r.get("chg_1d", 0)),
                "chg_1w": float(r.get("chg_1w", 0)),
                "chg_1m": float(r.get("chg_1m", 0)),
            })

    # ECB rows
    ecb_rows = []
    if not ecb_df.empty:
        for _, r in ecb_df.drop_duplicates(subset=["label"], keep="last").iterrows():
            val = float(r.get("value", 0))
            cat = r.get("category", "")
            chg_1w = float(r.get("chg_1w", 0)) if "chg_1w" in r else 0.0
            ecb_rows.append({
                **r.to_dict(),
                "value_fmt": f"{val:.2f}%" if cat == "rates" else f"{val:.4f}",
                "chg_1w": chg_1w,
                "chg_1w_fmt": f"{'▲' if chg_1w > 0 else '▼'} {abs(chg_1w):.2f}{'pp' if cat == 'rates' else ''}",
            })

    # Sector rows
    sector_rows = []
    if not sector_snap.empty:
        for ticker, r in sector_snap.iterrows():
            sector_rows.append({
                "ticker": ticker,
                "sector_name": r.get("sector_name", US_SECTOR_PROXIES.get(ticker, ticker)),
                "ret_1d": float(r.get("ret_1d", 0) or 0),
                "ret_1w": float(r.get("ret_1w", 0) or 0),
                "ret_1m": float(r.get("ret_1m", 0) or 0),
                "ret_3m": float(r.get("ret_3m", 0) or 0),
            })

    # Screen rows
    screen_rows = []
    if not top_candidates.empty:
        for ticker, r in top_candidates.head(10).iterrows():
            d = r.to_dict()
            d["ticker"] = ticker
            screen_rows.append(d)

    # Risk rows
    risk_rows = []
    if not risk_table.empty:
        for ticker, r in risk_table.iterrows():
            d = r.to_dict()
            d["ticker"] = ticker
            risk_rows.append(d)

    # Callout cards
    callout_cards = []
    if not top_candidates.empty:
        for ticker in list(top_candidates.index[:3]):
            row = top_candidates.loc[ticker] if ticker in top_candidates.index else pd.Series()
            sm_row = {}
            if not security_master_df.empty and "ticker" in security_master_df.columns:
                sm = security_master_df[security_master_df["ticker"] == ticker]
                if not sm.empty:
                    sm_row = sm.iloc[0].to_dict()
            callout_cards.append({
                "ticker": ticker,
                "rating": "Buy",  # from analyst overlay if available, else default
                "price": float(prices_df[ticker].dropna().iloc[-1]) if ticker in prices_df.columns else None,
                "target": sm_row.get("target_mean_price") or sm_row.get("price_target_mean"),
                "upside": float(row.get("target_upside", 0) or 0) if not row.empty else None,
                "forward_pe": float(row.get("forward_pe", float("nan")) or float("nan")) if not row.empty else None,
                "eps_growth": float(row.get("eps_growth_next_year", 0) or 0) if not row.empty else None,
                "research_score": float(row.get("research_score", 0) or 0) if not row.empty else None,
                "thesis": callouts.get(ticker, "") if isinstance(callouts, dict) else "",
            })

    # Executive summary bullets
    top_ticker = list(top_candidates.index[0]) if not top_candidates.empty else "N/A"
    exec_bullets = [
        f"Macro regime: {macro_regime_str} | Yield curve: {yield_curve_shape or 'N/A'}"
        + (f" | VIX at {vix_level:.1f}" if vix_level else ""),
        f"Top screen leader: {top_ticker} — research score {top_candidates.iloc[0].get('research_score', 0):.3f}" if not top_candidates.empty else "Screen produced no qualifying candidates.",
        f"US sector breadth: {sum(1 for r in sector_rows if r['ret_1w'] > 0)}/{len(sector_rows)} sectors positive on the week." if sector_rows else "Sector data unavailable.",
        f"Upcoming earnings catalysts: {', '.join([c['ticker'] for c in catalyst_rows[:4]])}." if catalyst_rows else "No near-term earnings catalysts identified.",
        f"Risk analytics: {len(risk_rows)} names screened | {sum(1 for r in risk_rows if r.get('sharpe', 0) > 1.0)} names with Sharpe > 1.0." if risk_rows else "Risk analytics unavailable.",
    ]
    exec_bullets = [b for b in exec_bullets if b]

    context = {
        "report_title": f"TRG Daily Research Note — {as_of}",
        "report_subtitle": "US Equities | Multi-Factor Screen | Risk Analytics | Macro Overlay | Valuation",
        "report_type": "Daily Research Note",
        "as_of_date": as_of,
        "macro_regime": macro_regime_str,
        "yield_curve_shape": yield_curve_shape,
        "vix_level": vix_level,
        "yield_curve": yield_curve_data,
        "yield_curve_narrative": (
            "Curve inversion persists — historically a leading recession indicator at current depth."
            if yield_curve_data.get("spread_10y2y", 0) < 0 else
            "Normal yield curve slope intact — no imminent recession signal from rates market."
        ),
        "top_screen_count": len(top_candidates),
        "executive_summary_bullets": exec_bullets,
        "us_macro_rows": us_macro_rows,
        "ecb_rows": ecb_rows,
        "sector_rows": sector_rows,
        "screen_rows": screen_rows,
        "risk_rows": risk_rows,
        "callout_cards": callout_cards,
        "catalyst_rows": catalyst_rows if isinstance(catalyst_rows, list) else [],
        "tactical_takeaways": tactical if isinstance(tactical, list) else [str(tactical)] if tactical else [],
        "analyst_overlays": [],
        "dcf_results": dcf_results,
        "charts": {k: str(v) for k, v in charts.items()},
    }

    # ── 5. Render outputs ─────────────────────────────────────────────────────
    from trg_workbench.reporting.pdf_renderer import render_html_only, render_research_note_pdf
    from trg_workbench.reporting.renderers import render_template, write_report
    from trg_workbench.reporting.templates import TEMPLATES_DIR as ORIG_TEMPLATES

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if "html" in output_formats or "pdf" in output_formats:
        html_path = OUTPUTS_DIR / f"research_note_{as_of}.html"
        p = render_html_only(context, html_path)
        outputs["html"] = p
        logger.info("HTML report: %s", p)

    if "pdf" in output_formats:
        pdf_path = OUTPUTS_DIR / f"research_note_{as_of}.pdf"
        p = render_research_note_pdf(context, pdf_path)
        outputs["pdf"] = p
        logger.info("PDF report: %s", p)

    if "markdown" in output_formats:
        try:
            md = render_template("daily_note.md.j2", context)
            md_path = OUTPUTS_DIR / f"daily_note_{as_of}.md"
            write_report(md, md_path)
            outputs["markdown"] = md_path
            logger.info("Markdown report: %s", md_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Markdown render failed: %s", exc)

    _log(
        "report_generated_v2",
        {
            "formats": list(outputs.keys()),
            "charts_count": len(charts),
            "dcf_tickers": [d["ticker"] for d in dcf_results],
        },
        as_of,
    )

    return outputs
