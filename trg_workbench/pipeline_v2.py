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

    Args:
        as_of: Date string YYYY-MM-DD.
        output_formats: List of formats to generate.
            Options: "html", "pdf", "markdown" (default: all three).

    Returns:
        Dict mapping format name to output file path.
    """
    # Create the master switch
    disable_prog = quiet or not sys.stdout.isatty()


    
    if output_formats is None:
        output_formats = ["html", "pdf", "markdown"]

    ensure_directories()
    outputs: Dict[str, Path] = {}

    # normalise as_of — v1 analytics expect date objects; file paths need strings
    as_of_str: str = as_of if isinstance(as_of, str) else as_of.isoformat()
    as_of_date: _date_type = _date_type.fromisoformat(as_of_str) if isinstance(as_of, str) else as_of
    as_of = as_of_str  # use string form for file paths / labels from here on

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

    # Build wide-format prices for v2 analytics (risk, charts)
    prices_wide = _prices_wide(prices_df)

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
        build_europe_summary,
        build_macro_summary,
        build_sector_summary,
        build_tactical_takeaways,
    )

    # Research dataset — correct arg order: (fundamentals, prices_long, metadata, date)
    research_df = build_research_dataset(
        fundamentals_df, prices_df, security_master_df, as_of_date
    )
    top_candidates = top_screen_candidates(research_df, limit=10)
    callouts = build_stock_callouts(research_df)
    catalyst_rows = build_catalyst_calendar(research_df, as_of_date)

    # Summaries for sector/europe/macro — these take long-format prices
    sector_tickers = list(US_SECTOR_PROXIES.keys())
    sector_summary = build_sector_summary(prices_df, as_of_date)
    europe_summary = build_europe_summary(prices_df, as_of_date)
    macro_summary  = build_macro_summary(ecb_df, as_of_date)
    tactical = build_tactical_takeaways(research_df, sector_summary, europe_summary, macro_summary)

    # sector_snap for chart generation — price snapshot of sector ETFs
    sector_snap = build_price_snapshot(prices_df, as_of_date)
    sector_snap = sector_snap[sector_snap.index.isin(sector_tickers)].copy()
    sector_snap["sector_name"] = sector_snap.index.map(US_SECTOR_PROXIES)

    # 2b. NEW: Risk analytics — run in subprocess to isolate from Windows AV/import conflicts
    logger.info("Computing risk metrics...")
    risk_table = pd.DataFrame()
    risk_csv = NORMALIZED_DIR / f"risk_metrics_{as_of}.csv"
    if not risk_csv.exists():
        try:
            import subprocess, sys as _sys
            risk_script = Path(__file__).parent / "_run_risk.py"
            # Write a helper script that computes risk and saves CSV
            risk_script.write_text(
                "import sys, pandas as pd\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from trg_workbench.pipeline_v2 import _load_prices, _prices_wide\n"
                "from trg_workbench.analytics.risk import build_risk_table\n"
                "import warnings; warnings.filterwarnings('ignore')\n"
                "prices_wide = _prices_wide(_load_prices(sys.argv[2]))\n"
                "rt = build_risk_table(prices_wide, market_col='XLK', rfr=0.053)\n"
                "rt.reset_index().to_csv(sys.argv[3], index=False)\n"
                "print('risk_ok', len(rt))\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [_sys.executable, str(risk_script),
                 str(Path(__file__).parent.parent), as_of, str(risk_csv)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                logger.info("Risk subprocess: %s", result.stdout.strip())
            else:
                logger.warning("Risk subprocess stderr: %s", result.stderr[-500:])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Risk analytics subprocess failed: %s", exc)

    if risk_csv.exists():
        try:
            risk_table = pd.read_csv(risk_csv).set_index("ticker")
            logger.info("Risk metrics loaded: %d tickers.", len(risk_table))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load risk CSV: %s", exc)

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

        # top_candidates has numeric index; get tickers from 'ticker' column
        _tc = "ticker" if "ticker" in top_candidates.columns else None
        top3 = list(top_candidates.head(3)[_tc].values) if (not top_candidates.empty and _tc) else []
        for ticker in tqdm(top3, desc="Computing valuations", disable=disable_prog):
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

                current_price = float(prices_wide[ticker].dropna().iloc[-1]) if (not prices_wide.empty and ticker in prices_wide.columns) else 0

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
                # If the progress bar is visible, we don't want to print to the console.
                if disable_prog:
                    # Bar is hidden, so show the info log
                    logger.info("Valuation complete for %s (Base: $%.2f)", ticker,scenarios["Base Case"]["intrinsic_value_per_share"])
                else:
                    # Bar is visible, so send this to debug (hidden from console by default)
                    logger.debug("Valuation complete for %s (Base: $%.2f)", ticker,scenarios["Base Case"]["intrinsic_value_per_share"])    
            except Exception as exc:  # noqa: BLE001
                logger.warning("Valuation failed for %s: %s", ticker, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Valuation module failed: %s", exc)

    # ── 3. Generate charts ────────────────────────────────────────────────────
    # Charts require matplotlib rendering which needs a full GUI-capable or
    # Agg-capable Python environment. Skipped gracefully in Git Bash / headless shells.
    # Run from Anaconda Prompt, Jupyter, or PowerShell (with conda activated) to generate.
    logger.info("Generating charts (skipped in headless/Git Bash environments)...")
    charts: Dict[str, Path] = {}
    # Load any pre-existing chart files from previous runs
    if CHARTS_DIR.exists():
        tag = as_of.replace("-", "_")
        for png in CHARTS_DIR.glob(f"*_{tag}.png"):
            key = png.stem.replace(f"_{tag}", "")
            charts[key] = png
        if charts:
            logger.info("Loaded %d existing chart files.", len(charts))

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

    # Screen rows — top_candidates has numeric index; ticker is a column
    screen_rows = []
    if not top_candidates.empty:
        for _, r in top_candidates.head(10).iterrows():
            d = r.to_dict()
            screen_rows.append(d)

    # Risk rows
    risk_rows = []
    if not risk_table.empty:
        for ticker, r in risk_table.iterrows():
            d = r.to_dict()
            d["ticker"] = ticker
            risk_rows.append(d)

    # Callout cards — top_candidates has ticker as a column (reset_index was called)
    callout_cards = []
    ticker_col = "ticker" if "ticker" in top_candidates.columns else None
    if not top_candidates.empty and ticker_col:
        for _, row in top_candidates.head(3).iterrows():
            ticker = str(row[ticker_col])
            sm_row = {}
            if not security_master_df.empty and "ticker" in security_master_df.columns:
                sm = security_master_df[security_master_df["ticker"] == ticker]
                if not sm.empty:
                    sm_row = sm.iloc[0].to_dict()
            callout_cards.append({
                "ticker": ticker,
                "rating": "Buy",
                "price": float(prices_wide[ticker].dropna().iloc[-1]) if (not prices_wide.empty and ticker in prices_wide.columns) else None,
                "target": sm_row.get("target_mean_price") or sm_row.get("price_target_mean"),
                "upside": float(row.get("target_upside", 0) or 0),
                "forward_pe": float(row.get("forward_pe", float("nan")) or float("nan")),
                "eps_growth": float(row.get("eps_growth_next_year", 0) or 0),
                "research_score": float(row.get("research_score", 0) or 0),
                "thesis": (callouts[int(row.name)] if isinstance(callouts, list) and int(row.name) < len(callouts) else ""),
            })

    # Executive summary bullets
    top_ticker = str(top_candidates.iloc[0]["ticker"]) if (not top_candidates.empty and ticker_col) else "N/A"
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

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if "html" in output_formats or "pdf" in output_formats:
        html_path = OUTPUTS_DIR / f"research_note_{as_of}.html"
        p = render_html_only(context, html_path)
        outputs["html"] = p
        logger.info("HTML report: %s", p)

    if "pdf" in output_formats:
        pdf_path = OUTPUTS_DIR / f"research_note_{as_of}.pdf"
        p = render_research_note_pdf(context, pdf_path, quiet=quiet)
        outputs["pdf"] = p
        logger.info("PDF report: %s", p)

    if "markdown" in output_formats:
        try:
            md = render_template("daily_note.md.j2", context)
            md_path = OUTPUTS_DIR / f"daily_note_{as_of}.md"
            write_report(md_path, md)
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
