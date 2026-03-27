"""
macro_us.py — US macro data via yfinance (free, no API key required).
Fetches: UST yields (2Y, 10Y), yield curve spread, VIX, DXY,
Gold, WTI crude oil, S&P 500 index.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None  # type: ignore


# Tickers available via yfinance for US macro
US_MACRO_TICKERS = {
    "ust_10y":   {"ticker": "^TNX",     "label": "UST 10Y Yield",     "category": "rates",       "unit": "pct"},
    "ust_2y":    {"ticker": "^IRX",     "label": "UST 3M / 2Y Proxy", "category": "rates",       "unit": "pct"},
    "ust_30y":   {"ticker": "^TYX",     "label": "UST 30Y Yield",     "category": "rates",       "unit": "pct"},
    "vix":       {"ticker": "^VIX",     "label": "VIX",               "category": "vol",         "unit": "index"},
    "dxy":       {"ticker": "DX-Y.NYB", "label": "DXY Dollar Index",  "category": "fx",          "unit": "index"},
    "gold":      {"ticker": "GC=F",     "label": "Gold ($/oz)",       "category": "commodities", "unit": "usd"},
    "wti":       {"ticker": "CL=F",     "label": "WTI Crude ($/bbl)", "category": "commodities", "unit": "usd"},
    "spx":       {"ticker": "^GSPC",    "label": "S&P 500",           "category": "equity",      "unit": "index"},
    "ndx":       {"ticker": "^NDX",     "label": "Nasdaq 100",        "category": "equity",      "unit": "index"},
}


class USMacroClient:
    """
    Fetches US macro data from Yahoo Finance.
    No API key required. Caches to CSV.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str, as_of: str) -> Path:
        return self.cache_dir / f"us_macro_{key}_{as_of}.csv"

    def fetch_series(
        self,
        key: str,
        as_of_date: Optional[str] = None,
        lookback_days: int = 365,
    ) -> pd.DataFrame:
        """Fetch a single macro series. Returns DataFrame with columns: date, value, label, category."""
        if yf is None:
            raise ImportError("yfinance is required: pip install yfinance")

        as_of = as_of_date or datetime.today().strftime("%Y-%m-%d")
        cache = self._cache_path(key, as_of)
        if cache.exists():
            return pd.read_csv(cache, parse_dates=["date"])

        meta = US_MACRO_TICKERS[key]
        start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = (datetime.strptime(as_of, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        try:
            raw = yf.download(meta["ticker"], start=start, end=end, auto_adjust=True, progress=False)
            if raw.empty:
                return pd.DataFrame(columns=["date", "value", "label", "category", "unit"])
            df = raw[["Close"]].copy()
            df.index = pd.to_datetime(df.index)
            df = df.reset_index()
            df.columns = ["date", "value"]
            df["label"] = meta["label"]
            df["category"] = meta["category"]
            df["unit"] = meta["unit"]
            df["key"] = key
            df["as_of_date"] = as_of
            df.to_csv(cache, index=False)
            return df
        except Exception as exc:  # noqa: BLE001
            return pd.DataFrame(columns=["date", "value", "label", "category", "unit"])

    def fetch_all(
        self,
        as_of_date: Optional[str] = None,
        lookback_days: int = 365,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch all US macro series. Returns dict of {key: DataFrame}."""
        results = {}
        for key in US_MACRO_TICKERS:
            results[key] = self.fetch_series(key, as_of_date, lookback_days)
            time.sleep(0.15)
        return results

    def build_snapshot(
        self,
        as_of_date: Optional[str] = None,
        lookback_days: int = 365,
    ) -> pd.DataFrame:
        """
        Build a macro snapshot DataFrame with latest values and changes.
        Returns rows: label, value, chg_1d, chg_1w, chg_1m, category.
        """
        all_data = self.fetch_all(as_of_date, lookback_days)
        rows = []

        for key, df in all_data.items():
            if df.empty or "value" not in df.columns:
                continue
            df = df.sort_values("date").dropna(subset=["value"])
            if df.empty:
                continue

            meta = US_MACRO_TICKERS[key]
            latest = float(df["value"].iloc[-1])

            def _chg(days: int) -> float:
                idx = max(0, len(df) - days - 1)
                prior = float(df["value"].iloc[idx])
                return latest - prior if meta["unit"] in ("pct", "index") else (latest / prior - 1 if prior != 0 else 0.0)

            rows.append({
                "key": key,
                "label": meta["label"],
                "category": meta["category"],
                "unit": meta["unit"],
                "value": round(latest, 4),
                "chg_1d": round(_chg(1), 4),
                "chg_1w": round(_chg(5), 4),
                "chg_1m": round(_chg(21), 4),
                "as_of": df["date"].iloc[-1].strftime("%Y-%m-%d") if hasattr(df["date"].iloc[-1], "strftime") else str(df["date"].iloc[-1]),
            })

        df_snap = pd.DataFrame(rows)
        if not df_snap.empty:
            cat_order = {"rates": 0, "vol": 1, "fx": 2, "commodities": 3, "equity": 4}
            df_snap["_sort"] = df_snap["category"].map(cat_order).fillna(9)
            df_snap = df_snap.sort_values("_sort").drop(columns=["_sort"])
        return df_snap

    def yield_curve_spread(self, as_of_date: Optional[str] = None) -> Dict:
        """
        Compute 10Y-2Y spread (yield curve shape indicator).
        Positive = normal, negative = inverted.
        """
        ust10 = self.fetch_series("ust_10y", as_of_date)
        ust2 = self.fetch_series("ust_2y", as_of_date)

        def _latest(df: pd.DataFrame) -> float:
            if df.empty:
                return float("nan")
            return float(df.sort_values("date")["value"].iloc[-1])

        t10 = _latest(ust10)
        t2 = _latest(ust2)
        spread = t10 - t2 if not (pd.isna(t10) or pd.isna(t2)) else float("nan")

        return {
            "ust_10y": t10,
            "ust_2y": t2,
            "spread_10y2y": round(spread, 4),
            "curve_shape": "Normal" if spread > 0 else "Inverted" if spread < 0 else "Flat",
        }

    def macro_regime(self, snapshot: pd.DataFrame) -> str:
        """
        Simple macro regime classifier based on VIX + yield curve.
        Returns one of: Risk-On, Risk-Off, Transitional.
        """
        if snapshot.empty:
            return "Unknown"
        vix_row = snapshot[snapshot["key"] == "vix"]
        vix = float(vix_row["value"].iloc[0]) if not vix_row.empty else float("nan")

        ust10_row = snapshot[snapshot["key"] == "ust_10y"]
        ust10 = float(ust10_row["value"].iloc[0]) if not ust10_row.empty else float("nan")

        if pd.isna(vix):
            return "Unknown"
        if vix < 15:
            return "Risk-On (Low Volatility)"
        if vix > 25:
            return "Risk-Off (Elevated Stress)"
        if 15 <= vix <= 25 and not pd.isna(ust10):
            return f"Transitional (VIX {vix:.1f}, 10Y {ust10:.2f}%)"
        return "Transitional"
