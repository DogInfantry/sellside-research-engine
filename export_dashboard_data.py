"""
export_dashboard_data.py: write dashboard_data.json for the Vercel dashboard (index.html).

Reuses the v2 pipeline (screening, value_ticker, risk, catalysts). Missing values are
written as null and shown as n/a on the page; nothing is invented.

Usage:
    python main_v2.py fetch-all --as-of 2026-09-22
    python export_dashboard_data.py --as-of 2026-09-22 --skip-fetch
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from trg_workbench.analytics.risk import build_risk_table
from trg_workbench.analytics.screening import build_research_dataset, top_screen_candidates
from trg_workbench.analytics.summaries import build_catalyst_calendar
from trg_workbench.analytics.valuation import reverse_dcf
from trg_workbench.config import NORMALIZED_DIR
from trg_workbench.io_utils import load_dataframe
from trg_workbench.pipeline_v2 import (
    _load_ecb,
    _load_fundamentals,
    _load_prices,
    _load_security_master,
    _prices_wide,
    fetch_data_v2,
    value_ticker,
)

WACCS = [7, 8, 9, 10]
TGS = [1.5, 2.0, 2.5, 3.0]
FACTORS = {"valuation": "valuation_score", "growth": "growth_score", "quality": "quality_score",
           "momentum": "momentum_score", "consensus": "forward_score"}


def num(x, scale: float = 1.0, nd: int = 2):
    """Finite float rounded to nd places, else None (JSON null)."""
    try:
        v = float(x) * scale
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def implied_growth(price: float, inputs: dict, wacc: float, tg: float):
    try:
        return reverse_dcf(current_price=price, shares_outstanding=inputs["shares_outstanding"],
                           net_debt=inputs["net_debt"], base_fcf=inputs["base_fcf"],
                           wacc=wacc, terminal_growth=tg)["implied_growth_rate"]
    except ValueError:
        return None


def ticker_block(row: pd.Series, px: pd.Series, val: dict | None, risk: pd.Series | None,
                 commentary: dict | None) -> dict:
    price = float(px.iloc[-1])
    prev = float(px.iloc[-2]) if len(px) > 1 else price
    upside = num(row.get("target_upside"))
    # ponytail: rating derived from analyst consensus target upside, +/-10% bands
    rating = "N/A" if upside is None else "BUY" if upside > 0.10 else "SELL" if upside < -0.10 else "HOLD"

    dcf = dict.fromkeys(["bear", "base", "bull", "wacc", "terminal_growth", "fcf_yield"])
    rdcf = {"implied_growth": None, "consensus_growth": num(row.get("forward_eps_growth"), 100, 1),
            "stretched": False, "sensitivity": []}
    if val:
        sc, inputs = val["scenarios"], val["inputs"]
        dcf = {
            "bear": num(sc["Bear Case"]["intrinsic_value_per_share"]),
            "base": num(sc["Base Case"]["intrinsic_value_per_share"]),
            "bull": num(sc["Bull Case"]["intrinsic_value_per_share"]),
            "wacc": num(inputs["wacc"], 100, 1),
            "terminal_growth": num(sc["Base Case"]["tgr_used"], 100, 1),
            "fcf_yield": num(inputs["base_fcf"] / row["market_cap"], 100, 1) if num(row.get("market_cap")) else None,
        }
        if val["reverse_dcf"]:
            rdcf["implied_growth"] = num(val["reverse_dcf"]["implied_growth_rate"], 100, 1)
        rdcf["sensitivity"] = [
            {"wacc": w, "tg": tg, "implied": num(implied_growth(price, inputs, w / 100, tg / 100), 100, 1)}
            for tg in TGS for w in WACCS
        ]
        if rdcf["implied_growth"] is not None and rdcf["consensus_growth"] is not None:
            rdcf["stretched"] = rdcf["implied_growth"] > rdcf["consensus_growth"]

    r = risk if risk is not None else {}
    return {
        "name": row.get("long_name") if isinstance(row.get("long_name"), str) else row.get("company_name"),
        "sector": row.get("sector") if isinstance(row.get("sector"), str) else None,
        "price": num(price),
        "price_change": num(price - prev),
        "price_change_pct": num((price / prev - 1) * 100) if prev else None,
        "market_cap_b": num(row.get("market_cap"), 1e-9, 0),
        "rating": rating,
        "price_target": num(row.get("target_mean")),
        "composite_score": num(row.get("research_score"), 100, 0),
        "dcf": dcf,
        "reverse_dcf": rdcf,
        "factors": {k: num(row.get(col), 100, 0) for k, col in FACTORS.items()},
        "risk": {
            "var_95": num(r.get("var_95_1d"), -100), "cvar": num(r.get("cvar_95_1d"), -100),
            "beta": num(r.get("beta")), "sharpe": num(r.get("sharpe")), "sortino": num(r.get("sortino")),
            "max_drawdown": num(r.get("max_drawdown"), 100),
            "vol_21d": num(r.get("vol_21d"), 100, 1), "vol_63d": num(r.get("vol_63d"), 100, 1),
        },
        "price_history": [{"date": d.strftime("%Y-%m-%d"), "price": num(p)} for d, p in px.tail(126).items()],
        "commentary": None if not commentary else {
            "tone": str(commentary.get("analyst_qa_tone", "")).upper() or None,
            "tone_score": num(commentary.get("tone_score")),
            "guidance": commentary.get("guidance_summary"),
            "themes": commentary.get("catalyst_flags") or [],
            "risk_flags": commentary.get("key_risks") or [],
        },
        "financials": {
            "revenue_growth_yoy": num(row.get("revenue_growth"), 100, 1),
            "net_margin": num(row.get("net_margin"), 100, 1),
            "pe_ttm": num(row.get("pe_ratio"), nd=1),
            "eps_next_yr": num(row.get("eps_avg_next_year")),
        },
    }


def macro_block(as_of: str) -> tuple[dict, dict]:
    """Latest values plus preformatted 1-day changes (bps for yields, % for commodities)."""
    path = NORMALIZED_DIR / f"us_macro_{as_of}.csv"
    m = load_dataframe(path).set_index("key") if path.exists() else pd.DataFrame()
    val = lambda k: num(m.at[k, "value"], nd=3) if k in m.index else None
    chg = lambda k: num(m.at[k, "chg_1d"], nd=4) if k in m.index else None

    def fmt(c, unit):
        if c is None:
            return None
        if unit:  # yields are in pct points (x100 = bps); commodity chg is a fraction (x100 = %)
            c *= 100
        return f"{c:+.{1 if unit else 2}f}{unit}"

    macro = {k: val(k) for k in ["ust_10y", "ust_2y", "ust_30y", "vix", "dxy", "wti"]}
    changes = {"ust_10y": fmt(chg("ust_10y"), "bps"), "ust_2y": fmt(chg("ust_2y"), "bps"),
               "vix": fmt(chg("vix"), ""), "dxy": fmt(chg("dxy"), ""), "wti": fmt(chg("wti"), "%")}
    if macro["ust_10y"] is not None and macro["ust_2y"] is not None:
        macro["spread_2s10s"] = round(macro["ust_10y"] - macro["ust_2y"], 3)
        if chg("ust_10y") is not None and chg("ust_2y") is not None:
            changes["spread_2s10s"] = fmt(chg("ust_10y") - chg("ust_2y"), "bps")

    fx = _load_ecb(as_of)
    fx = fx.loc[fx["label"] == "EURUSD"].sort_values("date") if not fx.empty else fx
    macro["eurusd"] = num(fx["value"].iloc[-1], nd=4) if len(fx) else None
    if len(fx) > 1:
        changes["eurusd"] = f"{fx['value'].iloc[-1] - fx['value'].iloc[-2]:+.4f}"
    return macro, changes


def build_dashboard(as_of: str, limit: int = 10) -> dict:
    as_of_date = date.fromisoformat(as_of)
    prices = _load_prices(as_of)
    fundamentals = _load_fundamentals(as_of)
    security_master = _load_security_master(as_of)
    if prices.empty or fundamentals.empty:
        raise SystemExit(f"No normalized data for {as_of}. Run: python main_v2.py fetch-all --as-of {as_of}")

    wide = _prices_wide(prices)
    research = build_research_dataset(fundamentals, prices, security_master, as_of_date)
    top = top_screen_candidates(research, limit=limit)
    tickers = [t for t in top["ticker"] if t in wide.columns]
    risk = build_risk_table(wide[tickers])

    commentary = {}
    try:
        from trg_workbench.llm.pipeline import build_management_commentary
        commentary = {c["ticker"]: c for c in build_management_commentary(tickers, as_of_date)}
    except Exception:  # noqa: BLE001  cached transcripts are optional
        pass

    blocks = {}
    for _, row in top.iterrows():
        t = row["ticker"]
        if t not in tickers:
            continue
        try:
            val = value_ticker(t, security_master, fundamentals, wide)
        except Exception:  # noqa: BLE001  same tolerance as build_research_report_v2
            val = None
        blocks[t] = ticker_block(row, wide[t].dropna(), val,
                                 risk.loc[t] if t in risk.index else None, commentary.get(t))

    corr_t = tickers[:5]
    corr = wide[corr_t].pct_change().tail(63).corr()
    macro, macro_chg = macro_block(as_of)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": as_of,
        "macro": macro,
        "macro_chg": macro_chg,
        "tickers": blocks,
        "correlation_matrix": {"tickers": corr_t,
                               "values": [[num(corr.at[a, b]) for b in corr_t] for a in corr_t]},
        "catalysts": [
            {"date": pd.Timestamp(c["next_earnings_date"]).strftime("%Y-%m-%d"), "ticker": c["ticker"],
             "event": "Earnings" + (f" (EPS est ${num(c['calendar_earnings_average'])})"
                                    if num(c.get("calendar_earnings_average")) is not None else ""),
             "type": "EARNINGS", "conviction": None}
            for c in build_catalyst_calendar(research, as_of_date, limit=6)
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Export dashboard_data.json")
    p.add_argument("--as-of", default=date.today().isoformat(), type=lambda s: date.fromisoformat(s).isoformat())
    p.add_argument("--output", default="dashboard_data.json")
    p.add_argument("--skip-fetch", action="store_true", help="use existing data/normalized files")
    args = p.parse_args()

    if not args.skip_fetch:
        fetch_data_v2(args.as_of)
    data = build_dashboard(args.as_of)
    if not data["tickers"]:
        print("ERROR: no tickers exported", file=sys.stderr)
        return 1
    # allow_nan=False: a NaN that slipped past num() fails here, not in the browser
    Path(args.output).write_text(json.dumps(data, indent=1, allow_nan=False, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {args.output}: {len(data['tickers'])} tickers as of {args.as_of}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
