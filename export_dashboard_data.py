"""
export_dashboard_data.py — Export pipeline data to JSON for Vercel dashboard.

This script runs the v2 pipeline and exports the data in the format expected by index.html.
Run this before deploying to Vercel to update the dashboard with live data.

Usage:
    python export_dashboard_data.py --as-of 2026-05-31
    python export_dashboard_data.py  # defaults to today
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _validate_date(s: str) -> str:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format '{s}'. Use YYYY-MM-DD.")


def _fetch_pipeline_data(as_of: str) -> Optional[Dict[str, Any]]:
    """Fetch data from the v2 pipeline."""
    try:
        from trg_workbench.pipeline_v2 import fetch_data_v2, build_research_report_v2
        from trg_workbench.io_utils import ensure_directories
        
        ensure_directories()
        
        # Fetch all data
        logger.info(f"Fetching data for {as_of}...")
        data = fetch_data_v2(as_of)
        
        return data
    except Exception as e:
        logger.error(f"Pipeline fetch failed: {e}")
        return None


def _transform_to_dashboard_format(pipeline_data: Dict[str, Any], as_of: str) -> Dict[str, Any]:
    """Transform pipeline data into the format expected by index.html."""
    from trg_workbench.analytics.screening import build_research_dataset, top_screen_candidates
    from trg_workbench.analytics.risk import build_risk_table
    from trg_workbench.analytics.valuation import (
        derive_dcf_inputs, dcf_sensitivity, football_field, reverse_dcf, scenario_analysis
    )
    from trg_workbench.llm.reasoner import analyze_transcript
    import pandas as pd
    from trg_workbench.config import DEFAULT_US_TICKERS, US_SECTOR_PROXIES
    
    # Load required dataframes
    prices_df = pd.read_csv(f"data/normalized/market_prices_{as_of}.csv", parse_dates=["date"])
    fundamentals_df = pd.read_csv(f"data/normalized/sec_fundamentals_{as_of}.csv")
    security_master_df = pd.read_csv(f"data/normalized/security_master_{as_of}.csv")
    
    # Pivot prices wide (column name is 'close' lowercase)
    prices_wide = prices_df.pivot_table(index="date", columns="ticker", values="close")
    prices_wide.index = pd.to_datetime(prices_wide.index)
    prices_wide = prices_wide.sort_index()
    
    # Build research dataset
    as_of_date = date.fromisoformat(as_of)
    research_df = build_research_dataset(fundamentals_df, prices_df, security_master_df, as_of_date)
    
    # Get top candidates (or use full watchlist)
    top_candidates = top_screen_candidates(research_df, limit=len(DEFAULT_US_TICKERS))
    
    # Compute risk metrics if not exists
    risk_path = Path(f"data/normalized/risk_metrics_{as_of}.csv")
    if not risk_path.exists():
        risk_df = build_risk_table(prices_wide, market_col="SPY")
        risk_df.to_csv(risk_path)
    else:
        risk_df = pd.read_csv(risk_path).set_index("ticker")
    
    # Build tickers dict
    tickers_dict = {}
    
    # Limit to available tickers in both price and fundamentals
    available_tickers = list(set(prices_wide.columns) & set(fundamentals_df["ticker"].unique()))
    
    for ticker in available_tickers[:10]:  # Limit to first 10 for dashboard performance
        try:
            # Get latest price
            price_series = prices_wide[ticker].dropna()
            if len(price_series) == 0:
                continue
            
            current_price = float(price_series.iloc[-1])
            
            # Price history (last 12 points)
            price_history_df = price_series.tail(12)
            price_history = [
                {"date": d.strftime("%Y-%m-%d"), "price": round(float(p), 2)}
                for d, p in price_history_df.items()
            ]
            
            # Get fundamentals row
            fund_row = fundamentals_df[fundamentals_df["ticker"] == ticker]
            if fund_row.empty:
                continue
            fund_row = fund_row.iloc[0]
            
            # Get security master row
            sm_row = security_master_df[security_master_df["ticker"] == ticker]
            sector = sm_row.iloc[0]["sector"] if not sm_row.empty and "sector" in sm_row.columns else "Unknown"
            company_name = sm_row.iloc[0]["name"] if not sm_row.empty and "name" in sm_row.columns else ticker
            
            # Market cap
            market_cap_b = float(fund_row.get("market_cap", 0)) / 1e9 if "market_cap" in fund_row.index else 0
            
            # Financial metrics
            revenue_ttm = float(fund_row.get("revenue_ttm", 0)) if "revenue_ttm" in fund_row.index else 0
            net_margin = float(fund_row.get("net_margin", 0)) * 100 if "net_margin" in fund_row.index else 0
            roe = float(fund_row.get("roe", 0)) * 100 if "roe" in fund_row.index else 0
            pe_ttm = float(fund_row.get("pe_ratio", 0)) if "pe_ratio" in fund_row.index else 0
            eps_next_yr = float(fund_row.get("eps_forward", 0)) if "eps_forward" in fund_row.index else 0
            debt_equity = float(fund_row.get("debt_to_equity", 0)) if "debt_to_equity" in fund_row.index else 0
            revenue_growth = float(fund_row.get("revenue_growth_yoy", 0)) * 100 if "revenue_growth_yoy" in fund_row.index else 0
            
            # DCF valuation
            try:
                inputs = derive_dcf_inputs(
                    sm_row.to_dict() if not sm_row.empty else {},
                    fund_row.to_dict() if not fund_row.empty else {}
                )
                
                if inputs["base_fcf"] > 0:
                    scenarios = scenario_analysis(
                        inputs["base_fcf"], inputs["base_growth"], 
                        inputs["wacc"], inputs["net_debt"], inputs["shares_outstanding"]
                    )
                    
                    sensitivity_df = dcf_sensitivity(
                        inputs["base_fcf"],
                        [inputs["base_growth"] * (0.85 ** i) for i in range(5)],
                        inputs["net_debt"],
                        inputs["shares_outstanding"]
                    )
                    
                    rdcf = reverse_dcf(current_price, inputs["net_debt"], inputs["shares_outstanding"], 
                                      inputs["base_fcf"], inputs["wacc"], inputs["terminal_growth"])
                    
                    implied_growth = float(rdcf["implied_growth"].iloc[0]) if len(rdcf) > 0 else 0
                    consensus_growth = inputs["base_growth"] * 100
                    
                    dcf_data = {
                        "bear": round(float(scenarios["bear"]["value_per_share"]), 2),
                        "base": round(float(scenarios["base"]["value_per_share"]), 2),
                        "bull": round(float(scenarios["bull"]["value_per_share"]), 2),
                        "wacc": round(inputs["wacc"] * 100, 1),
                        "terminal_growth": round(inputs["terminal_growth"] * 100, 1),
                        "fcf_yield": round(inputs["base_fcf"] / (inputs["market_cap"] + inputs["net_debt"]) * 100, 1) if (inputs["market_cap"] + inputs["net_debt"]) > 0 else 0
                    }
                    
                    # Sensitivity matrix
                    sensitivity_matrix = []
                    wacc_values = [7, 8, 9, 10]
                    tg_values = [1.5, 2.0, 2.5, 3.0]
                    for w in wacc_values:
                        for tg in tg_values:
                            try:
                                val = float(sensitivity_df.loc[w/100, tg/100])
                                sensitivity_matrix.append({
                                    "wacc": w,
                                    "tg": tg,
                                    "implied": round(val, 1)
                                })
                            except:
                                pass
                    
                    reverse_dcf_data = {
                        "implied_growth": round(implied_growth * 100, 1),
                        "consensus_growth": round(consensus_growth * 100, 1),
                        "stretched": implied_growth > consensus_growth * 1.2,
                        "sensitivity": sensitivity_matrix
                    }
                    
                    # Price target (use base DCF)
                    price_target = dcf_data["base"]
                    rating = "BUY" if price_target > current_price * 1.1 else "HOLD" if price_target > current_price * 0.9 else "SELL"
                else:
                    dcf_data = {"bear": 0, "base": 0, "bull": 0, "wacc": 0, "terminal_growth": 0, "fcf_yield": 0}
                    reverse_dcf_data = {"implied_growth": 0, "consensus_growth": 0, "stretched": False, "sensitivity": []}
                    price_target = current_price
                    rating = "HOLD"
            except Exception as e:
                logger.warning(f"DCF failed for {ticker}: {e}")
                dcf_data = {"bear": 0, "base": 0, "bull": 0, "wacc": 0, "terminal_growth": 0, "fcf_yield": 0}
                reverse_dcf_data = {"implied_growth": 0, "consensus_growth": 0, "stretched": False, "sensitivity": []}
                price_target = current_price
                rating = "HOLD"
            
            # Factor scores (simplified)
            valuation_score = min(100, max(0, 50 + (1/pe_ttm - 0.03) * 500)) if pe_ttm > 0 else 50
            growth_score = min(100, max(0, 50 + revenue_growth))
            quality_score = min(100, max(0, 50 + (roe - 15) * 2))
            momentum_score = min(100, max(0, 50 + (price_history[-1]["price"] / price_history[0]["price"] - 1) * 100)) if len(price_history) > 1 else 50
            consensus_score = 75  # Default
            
            factors = {
                "valuation": int(valuation_score),
                "growth": int(growth_score),
                "quality": int(quality_score),
                "momentum": int(momentum_score),
                "consensus": int(consensus_score)
            }
            
            composite_score = int((valuation_score * 0.2 + growth_score * 0.25 + quality_score * 0.25 + momentum_score * 0.15 + consensus_score * 0.15))
            
            # Risk metrics
            if ticker in risk_df.index:
                risk_row = risk_df.loc[ticker]
                risk_data = {
                    "var_95": round(float(risk_row.get("var_95", 0)) * 100, 2),
                    "cvar": round(float(risk_row.get("cvar_95", 0)) * 100, 2),
                    "beta": round(float(risk_row.get("beta", 1)), 2),
                    "sharpe": round(float(risk_row.get("sharpe", 0)), 2),
                    "sortino": round(float(risk_row.get("sortino", 0)), 2),
                    "max_drawdown": round(float(risk_row.get("max_drawdown", 0)) * 100, 2),
                    "vol_21d": round(float(risk_row.get("volatility_ann", 0)) * 100, 1),
                    "vol_63d": round(float(risk_row.get("volatility_ann", 0)) * 100 * 0.9, 1)
                }
            else:
                risk_data = {
                    "var_95": -2.0, "cvar": -2.5, "beta": 1.0,
                    "sharpe": 1.0, "sortino": 1.5, "max_drawdown": -15.0,
                    "vol_21d": 20.0, "vol_63d": 18.0
                }
            
            # Commentary (placeholder - would need LLM call)
            commentary = {
                "tone": "NEUTRAL",
                "guidance": f"{company_name} continues to show resilient performance in current market conditions.",
                "themes": ["Operational efficiency", "Market share gains", "Digital transformation"],
                "risk_flags": ["Macro headwinds", "Competitive pressure"],
                "tone_score": 0.55
            }
            
            financials = {
                "revenue_ttm_b": round(revenue_ttm / 1e9, 1) if revenue_ttm > 1e9 else round(revenue_ttm / 1e6, 1),
                "revenue_growth_yoy": round(revenue_growth, 1),
                "net_margin": round(net_margin, 1),
                "roe": round(roe, 1),
                "debt_equity": round(debt_equity, 2),
                "pe_ttm": round(pe_ttm, 1),
                "eps_next_yr": round(eps_next_yr, 2)
            }
            
            # Price change
            if len(price_history) >= 2:
                prev_price = price_history[-2]["price"]
                price_change = round(current_price - prev_price, 2)
                price_change_pct = round((price_change / prev_price) * 100, 2)
            else:
                price_change = 0
                price_change_pct = 0
            
            tickers_dict[ticker] = {
                "name": company_name,
                "sector": sector,
                "price": round(current_price, 2),
                "price_change": price_change,
                "price_change_pct": price_change_pct,
                "market_cap_b": round(market_cap_b, 0) if market_cap_b > 0 else 0,
                "rating": rating,
                "price_target": round(price_target, 0),
                "composite_score": composite_score,
                "dcf": dcf_data,
                "reverse_dcf": reverse_dcf_data,
                "factors": factors,
                "risk": risk_data,
                "price_history": price_history,
                "commentary": commentary,
                "financials": financials
            }
            
        except Exception as e:
            logger.warning(f"Failed to process {ticker}: {e}")
            continue
    
    # Macro data
    us_macro = pipeline_data.get("us_macro_snapshot", pd.DataFrame())
    yield_curve = pipeline_data.get("yield_curve", {})
    
    # Extract macro values
    def get_macro_value(series_id: str, default: float = 0) -> float:
        if not us_macro.empty and "series_id" in us_macro.columns and "value" in us_macro.columns:
            match = us_macro[us_macro["series_id"] == series_id]
            if not match.empty:
                try:
                    return float(match.iloc[0]["value"])
                except:
                    pass
        return default
    
    macro = {
        "ust_10y": get_macro_value("DGS10", 4.5),
        "ust_2y": get_macro_value("DGS2", 4.8),
        "ust_30y": get_macro_value("DGS30", 4.7),
        "vix": get_macro_value("^VIX", 15.0),
        "dxy": get_macro_value("DX-Y.NYB", 104.0),
        "wti": get_macro_value("CL=F", 78.0),
        "eurusd": get_macro_value("EURUSD=X", 1.08),
        "spread_2s10s": yield_curve.get("spread_2s10y", -0.3)
    }
    
    # Correlation matrix (for available tickers)
    available_for_corr = list(tickers_dict.keys())[:5]
    if len(available_for_corr) >= 2 and len(prices_wide) > 30:
        corr_prices = prices_wide[available_for_corr].dropna().tail(60)
        corr_matrix = corr_prices.corr().round(2)
        correlation_matrix = {
            "tickers": available_for_corr,
            "values": [corr_matrix.loc[t1, t2] for t1 in available_for_corr for t2 in available_for_corr]
        }
    else:
        # Default correlation matrix
        correlation_matrix = {
            "tickers": list(tickers_dict.keys())[:5],
            "values": [1.0] * (len(tickers_dict) ** 2)
        }
    
    # Catalyst calendar (placeholder)
    catalysts = [
        {"date": "2026-06-09", "ticker": "AAPL", "event": "WWDC — AI roadmap reveal", "type": "EVENT", "conviction": "HIGH"},
        {"date": "2026-07-15", "ticker": list(tickers_dict.keys())[0] if tickers_dict else "AAPL", "event": "Q2 Earnings", "type": "EARNINGS", "conviction": "HIGH"},
    ]
    
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "as_of": as_of,
        "macro": macro,
        "tickers": tickers_dict,
        "correlation_matrix": correlation_matrix,
        "catalysts": catalysts
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export dashboard data to JSON")
    parser.add_argument(
        "--as-of",
        type=_validate_date,
        default=datetime.today().strftime("%Y-%m-%d"),
        help="As-of date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="dashboard_data.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip fetching, use existing normalized data"
    )
    
    args = parser.parse_args()
    
    # Step 1: Fetch data if needed
    if not args.skip_fetch:
        pipeline_data = _fetch_pipeline_data(args.as_of)
        if pipeline_data is None:
            logger.error("Failed to fetch pipeline data. Run 'python main_v2.py fetch-all' first.")
            return 1
    else:
        pipeline_data = {"us_macro_snapshot": None, "yield_curve": {}}
    
    # Step 2: Transform to dashboard format
    logger.info("Transforming data to dashboard format...")
    dashboard_data = _transform_to_dashboard_format(pipeline_data, args.as_of)
    
    if not dashboard_data or not dashboard_data.get("tickers"):
        logger.error("No ticker data available. Check your normalized data files.")
        return 1
    
    # Step 3: Write JSON
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(dashboard_data, f, indent=2)
    
    logger.info(f"Dashboard data exported to {output_path}")
    logger.info(f"  Tickers: {len(dashboard_data['tickers'])}")
    logger.info(f"  As of: {dashboard_data['as_of']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
