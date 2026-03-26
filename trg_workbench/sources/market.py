from __future__ import annotations

import time
from datetime import date as date_type
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from trg_workbench.config import CACHE_DIR, DEFAULT_US_TICKERS, EUROPE_INDICES, US_SECTOR_PROXIES
from trg_workbench.io_utils import read_json, utc_now_iso, write_json


class MarketDataClient:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR / "market"

    @staticmethod
    def _all_tickers() -> list[str]:
        return sorted(
            set(DEFAULT_US_TICKERS)
            | set(US_SECTOR_PROXIES.keys())
            | set(EUROPE_INDICES.keys())
        )

    def fetch_price_history(self, as_of_date: date, refresh: bool = False) -> pd.DataFrame:
        cache_path = self.cache_dir / f"prices_{as_of_date.isoformat()}.csv"
        if cache_path.exists() and not refresh:
            frame = pd.read_csv(cache_path, parse_dates=["date"])
            return frame

        start_date = as_of_date - timedelta(days=400)
        end_date = as_of_date + timedelta(days=1)
        tickers = self._all_tickers()
        raw = yf.download(
            tickers=tickers,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw.empty:
            raise RuntimeError("Yahoo Finance returned no price history.")

        close_frame = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        volume_frame = raw["Volume"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Volume"]]

        close_long = (
            close_frame.reset_index()
            .melt(id_vars="Date", var_name="ticker", value_name="close")
            .rename(columns={"Date": "date"})
        )
        volume_long = (
            volume_frame.reset_index()
            .melt(id_vars="Date", var_name="ticker", value_name="volume")
            .rename(columns={"Date": "date"})
        )
        prices = close_long.merge(volume_long, on=["date", "ticker"], how="left")
        prices["date"] = pd.to_datetime(prices["date"])
        prices["source"] = "Yahoo Finance"
        prices["retrieved_at"] = utc_now_iso()
        prices["as_of_date"] = as_of_date.isoformat()
        prices = prices.dropna(subset=["close"]).sort_values(["ticker", "date"]).reset_index(drop=True)
        prices.to_csv(cache_path, index=False)
        return prices

    def fetch_metadata(self, as_of_date: date, refresh: bool = False) -> pd.DataFrame:
        cache_path = self.cache_dir / f"metadata_{as_of_date.isoformat()}.json"
        if cache_path.exists() and not refresh:
            cached = pd.DataFrame(read_json(cache_path))
            required_columns = {
                "eps_growth_next_year",
                "target_upside",
                "analyst_buy_ratio",
                "next_earnings_date",
            }
            if required_columns.issubset(cached.columns):
                return cached

        rows = []
        for ticker in self._all_tickers():
            instrument_group = (
                "us_equity"
                if ticker in DEFAULT_US_TICKERS
                else "sector_proxy"
                if ticker in US_SECTOR_PROXIES
                else "europe_index"
            )
            try:
                ticker_obj = yf.Ticker(ticker)
                info = ticker_obj.info
            except Exception:  # noqa: BLE001
                ticker_obj = None
                info = {}
            if instrument_group == "us_equity":
                earnings_estimate = self._extract_earnings_estimate(ticker_obj)
                recommendations = self._extract_recommendations(ticker_obj)
                analyst_targets = self._extract_price_targets(ticker_obj)
                calendar = self._extract_calendar(ticker_obj)
            else:
                earnings_estimate = {}
                recommendations = {}
                analyst_targets = {}
                calendar = {}
            rows.append(
                {
                    "ticker": ticker,
                    "long_name": info.get("longName")
                    or info.get("shortName")
                    or EUROPE_INDICES.get(ticker)
                    or US_SECTOR_PROXIES.get(ticker)
                    or ticker,
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "currency": info.get("currency"),
                    "exchange": info.get("exchange"),
                    "revenue_growth": info.get("revenueGrowth"),
                    "profit_margins": info.get("profitMargins"),
                    "return_on_equity": info.get("returnOnEquity"),
                    "total_revenue": info.get("totalRevenue"),
                    "net_income_to_common": info.get("netIncomeToCommon"),
                    "shares_outstanding": info.get("sharesOutstanding"),
                    "market_cap": info.get("marketCap"),
                    "trailing_pe": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "instrument_group": instrument_group,
                    "source": "Yahoo Finance",
                    "retrieved_at": utc_now_iso(),
                    "as_of_date": as_of_date.isoformat(),
                    **earnings_estimate,
                    **recommendations,
                    **analyst_targets,
                    **calendar,
                }
            )
            time.sleep(0.1)

        write_json(cache_path, [self._normalize_row(row) for row in rows])
        return pd.DataFrame(rows)

    def build_market_dataset(
        self,
        as_of_date: date,
        refresh: bool = False,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        prices = self.fetch_price_history(as_of_date, refresh=refresh)
        metadata = self.fetch_metadata(as_of_date, refresh=refresh)
        return prices, metadata

    @staticmethod
    def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
        normalized = {}
        for key, value in row.items():
            if hasattr(value, "item"):
                value = value.item()
            if isinstance(value, (date_type, pd.Timestamp)):
                value = pd.Timestamp(value).date().isoformat()
            normalized[key] = value
        return normalized

    @staticmethod
    def _extract_earnings_estimate(ticker_obj: yf.Ticker | None) -> dict[str, Any]:
        if ticker_obj is None:
            return {}
        try:
            frame = ticker_obj.get_earnings_estimate()
        except Exception:  # noqa: BLE001
            return {}
        if frame is None or frame.empty:
            return {}
        payload: dict[str, Any] = {}
        period_map = {
            "0y": "current_year",
            "+1y": "next_year",
            "0q": "current_quarter",
            "+1q": "next_quarter",
        }
        for period, suffix in period_map.items():
            if period not in frame.index:
                continue
            row = frame.loc[period]
            payload[f"eps_avg_{suffix}"] = row.get("avg")
            payload[f"eps_growth_{suffix}"] = row.get("growth")
            payload[f"eps_analysts_{suffix}"] = row.get("numberOfAnalysts")
        return payload

    @staticmethod
    def _extract_recommendations(ticker_obj: yf.Ticker | None) -> dict[str, Any]:
        if ticker_obj is None:
            return {}
        try:
            frame = ticker_obj.get_recommendations_summary()
        except Exception:  # noqa: BLE001
            return {}
        if frame is None or frame.empty:
            return {}
        if "period" not in frame.columns:
            return {}
        indexed = frame.set_index("period")

        def ratios(period: str) -> tuple[float | None, float | None]:
            if period not in indexed.index:
                return None, None
            row = indexed.loc[period]
            total = row[["strongBuy", "buy", "hold", "sell", "strongSell"]].sum()
            if not total:
                return None, None
            buy_ratio = (row["strongBuy"] + row["buy"]) / total
            hold_ratio = row["hold"] / total
            return buy_ratio, hold_ratio

        buy_ratio_0m, hold_ratio_0m = ratios("0m")
        buy_ratio_3m, _ = ratios("-3m")
        return {
            "analyst_buy_ratio": buy_ratio_0m,
            "analyst_hold_ratio": hold_ratio_0m,
            "analyst_buy_ratio_change_3m": (
                buy_ratio_0m - buy_ratio_3m
                if buy_ratio_0m is not None and buy_ratio_3m is not None
                else None
            ),
        }

    @staticmethod
    def _extract_price_targets(ticker_obj: yf.Ticker | None) -> dict[str, Any]:
        if ticker_obj is None:
            return {}
        try:
            payload = ticker_obj.get_analyst_price_targets()
        except Exception:  # noqa: BLE001
            return {}
        if not payload:
            return {}
        current = payload.get("current")
        mean_target = payload.get("mean")
        target_upside = None
        if current and mean_target:
            target_upside = (mean_target / current) - 1
        return {
            "target_current": current,
            "target_mean": mean_target,
            "target_high": payload.get("high"),
            "target_low": payload.get("low"),
            "target_median": payload.get("median"),
            "target_upside": target_upside,
        }

    @staticmethod
    def _extract_calendar(ticker_obj: yf.Ticker | None) -> dict[str, Any]:
        if ticker_obj is None:
            return {}
        try:
            calendar = ticker_obj.calendar
        except Exception:  # noqa: BLE001
            return {}
        if not calendar:
            return {}

        earnings_date = calendar.get("Earnings Date")
        if isinstance(earnings_date, list):
            earnings_date = earnings_date[0] if earnings_date else None
        if isinstance(earnings_date, pd.Timestamp):
            earnings_date = earnings_date.date()

        return {
            "next_earnings_date": earnings_date.isoformat() if isinstance(earnings_date, date_type) else None,
            "calendar_earnings_average": calendar.get("Earnings Average"),
            "calendar_earnings_high": calendar.get("Earnings High"),
            "calendar_earnings_low": calendar.get("Earnings Low"),
            "calendar_revenue_average": calendar.get("Revenue Average"),
            "calendar_revenue_high": calendar.get("Revenue High"),
            "calendar_revenue_low": calendar.get("Revenue Low"),
        }
