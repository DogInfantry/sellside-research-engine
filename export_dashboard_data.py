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

import numpy as np
import pandas as pd

from trg_workbench.analytics.risk import build_risk_table
from trg_workbench.analytics.screening import RETURN_WINDOWS, build_research_dataset, top_screen_candidates
from trg_workbench.analytics.summaries import build_catalyst_calendar
from trg_workbench.analytics.valuation import BALANCE_SHEET_INDUSTRIES, build_comps_table, football_field, reverse_dcf
from trg_workbench.config import CACHE_DIR, NORMALIZED_DIR, US_SECTOR_PROXIES
from trg_workbench.io_utils import load_dataframe
from trg_workbench.pipeline_v2 import (
    _load_ecb,
    _load_fundamentals,
    _load_prices,
    _load_quarterly,
    _load_security_master,
    _load_sentiment,
    _market_ranges,
    _prices_wide,
    fetch_data_v2,
    value_bank,
    value_ticker,
)

WACC_STEPS = [-2, -1, 0, 1, 2]  # pct points around each ticker's own WACC
TGS = [1.5, 2.0, 2.5, 3.0]
FACTORS = {"valuation": "valuation_score", "growth": "growth_score", "quality": "quality_score",
           "momentum": "momentum_score", "consensus": "forward_score"}
# yfinance sector -> SPDR sector ETF already fetched with the prices (no XLB: Basic Materials shows n/a)
SECTOR_ETF = {"Technology": "XLK", "Communication Services": "XLC", "Consumer Cyclical": "XLY",
              "Consumer Defensive": "XLP", "Financial Services": "XLF", "Healthcare": "XLV", "Energy": "XLE",
              "Industrials": "XLI", "Real Estate": "XLRE", "Utilities": "XLU"}
# comps column -> display scale (100 = shown in %)
VS_SECTOR = {"fwd_pe": 1, "ev_ebitda": 1, "ev_sales": 1, "peg": 1, "fcf_yield": 100, "growth": 100,
             "margin": 100, "roe": 100, "net_debt_ebitda": 1}


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


def sector_context(comps: pd.DataFrame, ticker: str) -> dict:
    """Stock vs the median of its sector peers in the fetched US universe (the stock itself excluded)."""
    me = comps[comps["ticker"] == ticker]
    sector = me["sector"].iloc[0] if len(me) else None
    peers = comps[(comps["sector"] == sector) & (comps["ticker"] != ticker)]
    out = {"etf": SECTOR_ETF.get(sector), "peers": len(peers)}
    for key, scale in VS_SECTOR.items():
        has = key in comps
        vals = peers[key].dropna() if has else peers.iloc[:0]
        out[key] = num(me[key].iloc[0], scale) if has and len(me) else None
        # a median needs at least half the peers: one asset manager is not the median of seven banks and brokers
        out[f"{key}_median"] = num(vals.median(), scale) if len(vals) and 2 * len(vals) >= len(peers) else None
    return out


def sector_block(wide: pd.DataFrame) -> dict:
    """Sector ETF and S&P 500 returns over US sessions (days any of them has a close). Yahoo drops single days
    per series (09-22 for XLK and SPX but not XLE): a window missing its start or end close is n/a, never
    stretched back to an earlier close, so every value covers exactly its window."""
    px = wide[[c for c in [*US_SECTOR_PROXIES, "SPX"] if c in wide]].dropna(how="all")
    if len(px) < 64:
        return {"as_of": None, "rows": []}
    rets = {k: px.iloc[-1] / px.iloc[-1 - n] - 1 for k, n in RETURN_WINDOWS.items()}  # NaN if a close is missing
    rets["ret_ytd"] = px.iloc[-1] / px[px.index.year < px.index[-1].year].iloc[-1] - 1
    rets["prior_2m"] = px.iloc[-22] / px.iloc[-64] - 1  # 3M to 1M ago: does not overlap the last month
    return {"as_of": px.index[-1].strftime("%Y-%m-%d"), "rows": [
        {"etf": t, "name": US_SECTOR_PROXIES.get(t, "S&P 500"), **{k: num(r[t], 100, 1) for k, r in rets.items()}}
        for t in px.columns]}


def pe_growth_fit(comps: pd.DataFrame) -> dict | None:
    """OLS line of forward P/E on consensus revenue growth (pp) across the universe; None under 3 names."""
    d = comps[(comps["fwd_pe"] > 0) & comps["growth"].notna()]
    if len(d) < 3:
        return None
    x, y = d["growth"] * 100, d["fwd_pe"]
    slope, intercept = np.polyfit(x, y, 1)
    return {"slope": num(slope, nd=3), "intercept": num(intercept), "r2": num(np.corrcoef(x, y)[0, 1] ** 2), "n": len(d)}


def quarterly_block(q: pd.DataFrame, bank: bool) -> dict:
    """Reported quarters (Yahoo keeps 4 to 7; up to 8 shown), plus TTM DuPont ROE and earnings quality from the
    last 4 quarters and the latest balance sheet. Under 4 quarters there is no TTM. Earnings quality is n/a for
    banks, brokers and insurers: their operating cash flow is funding, not earnings."""
    cols = ["revenue", "eps", "net_income", "operating_income", "ocf", "capex", "total_assets", "equity"]
    q = q.reindex(columns=["period_end", *cols]).dropna(subset=["period_end"]).sort_values("period_end").copy()
    q[cols] = q[cols].apply(pd.to_numeric, errors="coerce")
    ratio = lambda a, b, scale=1, nd=2: num(a / b, scale, nd) if b else None  # NaN in, None out
    bs = q.dropna(subset=["total_assets", "equity"])
    # Yahoo's balance sheet reaches further back than its income statement: those dates are not quarters
    q = q.dropna(subset=["revenue", "eps", "net_income"], how="all").tail(8)
    # TTM: the last 4 quarters with revenue and net income, and only if back to back (about 9 months first to last)
    full = q.dropna(subset=["revenue", "net_income"]).tail(4)
    ttm_ok = len(full) == 4 and (full["period_end"].iloc[-1] - full["period_end"].iloc[0]).days <= 300
    t = full[["revenue", "net_income", "ocf", "capex"]].sum(min_count=4) if ttm_ok else {}
    rev, ni, ocf, capex = (t.get(k, float("nan")) for k in ["revenue", "net_income", "ocf", "capex"])
    if ttm_ok:
        bs = bs[bs["period_end"] <= full["period_end"].iloc[-1]]
    assets, equity = (bs["total_assets"].iloc[-1], bs["equity"].iloc[-1]) if len(bs) else (float("nan"),) * 2
    return {
        "quarters": [{"period": r.period_end.strftime("%Y-%m-%d"), "revenue_b": num(r.revenue, 1e-9), "eps": num(r.eps),
                      # a broker's "operating income" leaves out interest expense, its main cost: not comparable
                      "op_margin": None if bank else ratio(r.operating_income, r.revenue, 100, 1)} for r in q.itertuples()],
        "dupont": {"net_margin": ratio(ni, rev, 100, 1), "asset_turnover": ratio(rev, assets, nd=3),
                   "equity_multiplier": ratio(assets, equity), "roe": ratio(ni, equity, 100, 1),
                   "through": full["period_end"].iloc[-1].strftime("%Y-%m-%d") if ttm_ok else None},
        "quality": {"cfo_ni": ratio(ocf, ni) if not bank and ni > 0 else None,
                    "capex_pct_revenue": None if bank else ratio(-capex, rev, 100, 1),
                    "fcf_margin": None if bank else ratio(ocf + capex, rev, 100, 1)},
    }


def spread_on_shared_dates(ten: pd.Series, two: pd.Series) -> tuple:
    """10Y minus 2Y on the last day both have a value, and its change since the previous shared day.
    FRED's 2Y lags Yahoo's 10Y by a day and each skips days the other has."""
    both = pd.concat([ten, two], axis=1, sort=True).dropna()
    if len(both) < 2:
        return None, None, None
    s = both.iloc[:, 0] - both.iloc[:, 1]
    return both.index[-1].strftime("%Y-%m-%d"), round(float(s.iloc[-1]), 3), round(float(s.iloc[-1] - s.iloc[-2]), 4)


def sentiment_block(s: dict | None, sm_row: dict) -> dict:
    """Next fiscal year EPS revisions, the last 4 earnings surprises, the recommendation trend, 6 month insider
    activity and short interest. Missing pieces stay None (n/a); a % change needs a positive base."""
    s = s or {}
    chg = lambda a, b: num((a / b - 1) * 100, nd=1) if num(a) is not None and num(b) is not None and b > 0 else None
    count = lambda v: int(v) if num(v) is not None else None
    trend = (s.get("eps_trend") or {}).get("+1y") or {}
    revs = (s.get("eps_revisions") or {}).get("+1y") or {}
    ins = s.get("insider") or {}
    net, held = num(ins.get("net_shares")), num(ins.get("held"))
    before = held - net if net is not None and held is not None else None  # insider holdings 6 months ago
    return {
        "eps_next_fy": num(trend.get("current")),
        "rev_30d": chg(trend.get("current"), trend.get("30daysAgo")),
        "rev_90d": chg(trend.get("current"), trend.get("90daysAgo")),
        "up_30d": count(revs.get("upLast30days")), "down_30d": count(revs.get("downLast30days")),
        "surprises": [{"quarter": q.get("quarter"), "actual": num(q.get("actual")), "estimate": num(q.get("estimate")),
                       "surprise_pct": num(q.get("surprise_pct"), 100, 1)} for q in (s.get("surprises") or [])][-4:],
        "recommendations": [{"period": r.get("period"), **{k: count(r.get(k)) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}}
                            for r in (s.get("recommendations") or [])],
        "insider": {"purchases": count(ins.get("purchases")), "sales": count(ins.get("sales")),
                    "net_shares": count(ins.get("net_shares")),
                    # computed here: Yahoo's own % can carry the wrong sign
                    "net_pct": num(net / before * 100, nd=1) if before and before > 0 else None},
        "short": {"pct_float": num(sm_row.get("short_pct_float"), 100, 2), "days_to_cover": num(sm_row.get("short_ratio"), nd=1),
                  "change_pct": chg(sm_row.get("shares_short"), sm_row.get("shares_short_prior"))},
    }


def ticker_block(row: pd.Series, px: pd.Series, val: dict | None, risk: pd.Series | None,
                 commentary: dict | None, bank: dict | None = None, market_ff: dict | None = None) -> dict:
    price = float(px.iloc[-1])
    prev = float(px.iloc[-2]) if len(px) > 1 else price
    upside = num(row.get("target_upside"))
    # ponytail: rating derived from analyst consensus target upside, +/-10% bands
    rating = "N/A" if upside is None else "BUY" if upside > 0.10 else "SELL" if upside < -0.10 else "HOLD"

    dcf = {**dict.fromkeys(["bear", "base", "bull", "wacc", "terminal_growth", "fcf_yield", "rf"]), "grid": []}
    rdcf = {"implied_growth": None, "consensus_growth": None, "stretched": False, "sensitivity": []}
    if val:
        sc, inputs = val["scenarios"], val["inputs"]
        dcf = {
            "bear": num(sc["Bear Case"]["intrinsic_value_per_share"]),
            "base": num(sc["Base Case"]["intrinsic_value_per_share"]),
            "bull": num(sc["Bull Case"]["intrinsic_value_per_share"]),
            "wacc": num(inputs["wacc"], 100, 1),
            "terminal_growth": num(sc["Base Case"]["tgr_used"], 100, 1),
            "fcf_yield": num(inputs["base_fcf"] / row["market_cap"], 100, 1) if num(row.get("market_cap")) else None,
            "rf": num(inputs["risk_free_rate"], 100),
            # value per share across WACC and terminal growth, centred on this ticker's WACC and 2.5%
            "grid": [{"wacc": num(w, 100, 1), "tg": num(g, 100, 1), "value": num(val["sensitivity_df"].iat[i, j])}
                     for j, g in enumerate(val["sensitivity_axes"]["tg"]) for i, w in enumerate(val["sensitivity_axes"]["wacc"])],
        }
        if val["reverse_dcf"]:
            rdcf["implied_growth"] = num(val["reverse_dcf"]["implied_growth_rate"], 100, 1)
        # same consensus revenue growth the DCF uses; n/a when there is no estimate
        rdcf["consensus_growth"] = num(inputs.get("consensus_growth"), 100, 1)
        waccs = [round(dcf["wacc"] + s, 1) for s in WACC_STEPS]
        rdcf["sensitivity"] = [
            {"wacc": w, "tg": tg, "implied": num(implied_growth(price, inputs, w / 100, tg / 100), 100, 1)}
            for tg in TGS for w in waccs
        ]
        if rdcf["implied_growth"] is not None and rdcf["consensus_growth"] is not None:
            rdcf["stretched"] = rdcf["implied_growth"] > rdcf["consensus_growth"]

    r = risk if risk is not None else {}
    ff = (val or bank or {}).get("football_field") or market_ff
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
        "football": [{"method": k, "low": num(lo), "mid": num(mid), "high": num(hi)}
                     for k, (lo, mid, hi) in ff["methods"].items()] if ff else [],
        "residual_income": None if not bank else {
            "value": num(bank["value_per_share"]), "justified_pb": num(bank["justified_pb"]),
            "actual_pb": num(bank["actual_pb"]), "roe": num(bank["roe"], 100, 1), "book_value": num(bank["book_value"]),
            "cost_of_equity": num(bank["cost_of_equity"], 100, 1), "growth": num(bank["growth"], 100, 1)},
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


def macro_block(as_of: str) -> tuple[dict, dict, dict]:
    """Latest values, preformatted 1-day changes (bps for yields, % for commodities) and each series' last date.
    The 2Y comes from FRED and can lag Yahoo's 10Y by a day, so the page shows its date."""
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

    macro = {k: val(k) for k in ["ust_10y", "ust_2y", "tbill_3m", "ust_30y", "vix", "dxy", "wti"]}
    changes = {"ust_10y": fmt(chg("ust_10y"), "bps"), "ust_2y": fmt(chg("ust_2y"), "bps"),
               "tbill_3m": fmt(chg("tbill_3m"), "bps"),
               "vix": fmt(chg("vix"), ""), "dxy": fmt(chg("dxy"), ""), "wti": fmt(chg("wti"), "%")}
    dates = {k: str(m.at[k, "as_of"]) for k in macro if k in m.index and "as_of" in m}
    # the spread on the last day both legs have (never a stale 2Y against today's 10Y), from the series caches
    legs = [CACHE_DIR / f"us_macro_{k}_{as_of}.csv" for k in ("ust_10y", "ust_2y")]
    if all(p.exists() for p in legs):
        ten, two = (load_dataframe(p, parse_dates=["date"]).set_index("date")["value"] for p in legs)
        dates["spread_2s10s"], macro["spread_2s10s"], change = spread_on_shared_dates(ten, two)
        changes["spread_2s10s"] = fmt(change, "bps")

    fx = _load_ecb(as_of)
    fx = fx.loc[fx["label"] == "EURUSD"].sort_values("date") if not fx.empty else fx
    macro["eurusd"] = num(fx["value"].iloc[-1], nd=4) if len(fx) else None
    if len(fx) > 1:
        changes["eurusd"] = f"{fx['value'].iloc[-1] - fx['value'].iloc[-2]:+.4f}"
    return macro, changes, dates


def build_dashboard(as_of: str, limit: int = 10) -> dict:
    as_of_date = date.fromisoformat(as_of)
    prices = _load_prices(as_of)
    fundamentals = _load_fundamentals(as_of)
    security_master = _load_security_master(as_of)
    if prices.empty or fundamentals.empty:
        raise SystemExit(f"No normalized data for {as_of}. Run: python main_v2.py fetch-all --as-of {as_of}")

    wide = _prices_wide(prices)
    macro, macro_chg, macro_as_of = macro_block(as_of)
    # live rates: 10Y for the DCF discount rate, 3M bill for Sharpe/Sortino; without them the old 5.3% default stays
    dcf_rf = macro["ust_10y"] / 100 if macro["ust_10y"] is not None else 0.053
    cash_rf = macro["tbill_3m"] / 100 if macro["tbill_3m"] is not None else 0.053
    research = build_research_dataset(fundamentals, prices, security_master, as_of_date)
    top = top_screen_candidates(research, limit=limit)
    tickers = [t for t in top["ticker"] if t in wide.columns]
    universe = [t for t in research["ticker"] if t in wide.columns]  # the 21 stock universe, for comps
    # S&P 500 level cached by macro_us during fetch-all; it is the market column for beta and the benchmark line
    spx_path = CACHE_DIR / f"us_macro_spx_{as_of}.csv"
    if spx_path.exists():
        wide["SPX"] = load_dataframe(spx_path, parse_dates=["date"]).set_index("date")["value"].reindex(wide.index)
    risk = build_risk_table(wide[universe + [c for c in ["SPX"] if c in wide]], market_col="SPX", rfr=cash_rf)

    commentary = {}
    try:
        from trg_workbench.llm.pipeline import build_management_commentary
        commentary = {c["ticker"]: c for c in build_management_commentary(tickers, as_of_date)}
    except Exception:  # noqa: BLE001  cached transcripts are optional
        pass

    def safe_value(t):
        try:
            return value_ticker(t, security_master, fundamentals, wide, risk_free_rate=dcf_rf)
        except Exception:  # noqa: BLE001  same tolerance as build_research_report_v2
            return None

    vals = {t: safe_value(t) for t in universe}
    comps = build_comps_table(security_master).merge(
        research[["ticker", "market_cap", "ret_3m", "research_score", *FACTORS.values()]], on="ticker", how="left")
    comps["vol_63d"] = comps["ticker"].map(risk["vol_63d"])
    # same FCF yield as the KPI tile (DCF base FCF over market cap); n/a where there is no DCF
    base_fcf = pd.to_numeric(comps["ticker"].map(lambda t: vals[t]["inputs"]["base_fcf"] if vals.get(t) else None))
    comps["fcf_yield"] = base_fcf / comps["market_cap"].where(comps["market_cap"] > 0)

    quarterly = _load_quarterly(as_of)
    sm_rows = security_master.drop_duplicates("ticker").set_index("ticker")
    sentiment = _load_sentiment(as_of)
    blocks = {}
    for _, row in top.iterrows():
        t = row["ticker"]
        if t not in tickers:
            continue
        bank = value_bank(t, security_master, wide, risk_free_rate=dcf_rf)
        # analyst and 52 week ranges need no model: keep them when neither valuation applies
        market = None if vals.get(t) or bank else football_field(
            t, float(wide[t].dropna().iloc[-1]), **_market_ranges(sm_rows.loc[t].to_dict() if t in sm_rows.index else {}))
        blocks[t] = ticker_block(row, wide[t].dropna(), vals.get(t), risk.loc[t] if t in risk.index else None,
                                 commentary.get(t), bank, market)
        blocks[t]["vs_sector"] = sector_context(comps, t)
        is_bank = str(row.get("industry", "")).startswith(BALANCE_SHEET_INDUSTRIES)
        blocks[t]["sentiment"] = sentiment_block(sentiment.get(t), sm_rows.loc[t].to_dict() if t in sm_rows.index else {})
        blocks[t].update(quarterly_block(quarterly[quarterly["ticker"] == t] if len(quarterly) else quarterly, is_bank))

    # same shape and window as price_history, so the page can rebase stock, sector and market together
    bench = {"SPX"} | {b["vs_sector"]["etf"] for b in blocks.values()}
    benchmarks = {c: [{"date": d.strftime("%Y-%m-%d"), "price": num(p)} for d, p in wide[c].dropna().tail(126).items()]
                  for c in sorted(b for b in bench if b in wide)}

    corr_t = list(blocks)
    corr = wide[corr_t].pct_change().tail(63).corr()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": as_of,
        "macro": macro,
        "macro_chg": macro_chg,
        "macro_as_of": macro_as_of,
        "rates": {"dcf_rf": num(dcf_rf, 100), "dcf_rf_source": "UST 10Y" if macro["ust_10y"] is not None else "default",
                  "cash_rf": num(cash_rf, 100), "cash_rf_source": "UST 3M bill" if macro["tbill_3m"] is not None else "default"},
        "tickers": blocks,
        "benchmarks": benchmarks,
        "comps": {c["ticker"]: {
            "sector": c["sector"] if isinstance(c["sector"], str) else None,
            **{k: num(c[k], scale) for k, scale in VS_SECTOR.items()},
            "vol_63d": num(c["vol_63d"], 100, 1), "ret_3m": num(c["ret_3m"], 100, 1),
            "composite": num(c["research_score"], 100, 0),
            "factors": {k: num(c[col], 100, 0) for k, col in FACTORS.items()},
        } for _, c in comps.iterrows()},
        "pe_growth_fit": pe_growth_fit(comps),
        "sectors": sector_block(wide),
        "correlation_matrix": {"tickers": corr_t,
                               "values": [[num(corr.at[a, b]) for b in corr_t] for a in corr_t]},
        "catalysts": [
            {"date": pd.Timestamp(c["next_earnings_date"]).strftime("%Y-%m-%d"), "ticker": c["ticker"],
             "event": "Earnings" + (f" (EPS est ${num(c['calendar_earnings_average']):.2f})"
                                    if num(c.get("calendar_earnings_average")) is not None else ""),
             "type": "EARNINGS", "conviction": None}
            # only names shown on the page; the calendar itself spans the whole universe
            for c in [c for c in build_catalyst_calendar(research, as_of_date, limit=len(research))
                      if c["ticker"] in blocks][:6]
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
