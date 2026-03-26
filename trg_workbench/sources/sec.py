from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from trg_workbench.config import CACHE_DIR, SEC_COMPANYFACTS_URL, SEC_TICKERS_URL, SEC_USER_AGENT
from trg_workbench.io_utils import read_json, utc_now_iso, write_json


ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "Revenues",
]
NET_INCOME_CONCEPTS = ["NetIncomeLoss", "ProfitLoss"]
EQUITY_CONCEPTS = [
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "StockholdersEquity",
]
SHARE_CONCEPTS = [
    "EntityCommonStockSharesOutstanding",
    "CommonStockSharesOutstanding",
]
ASSET_CONCEPTS = ["Assets"]


class SECClient:
    def __init__(self, cache_dir: Path | None = None, user_agent: str = SEC_USER_AGENT) -> None:
        self.cache_dir = cache_dir or CACHE_DIR / "sec"
        self.companyfacts_dir = self.cache_dir / "companyfacts"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def _get_json(self, url: str, cache_path: Path, refresh: bool = False) -> Any:
        if cache_path.exists() and not refresh:
            return read_json(cache_path)

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                payload = response.json()
                write_json(cache_path, payload)
                return payload
            except requests.RequestException as exc:
                last_error = exc
                time.sleep((attempt + 1) * 1.5)
        raise RuntimeError(f"SEC request failed for {url}") from last_error

    def fetch_ticker_map(self, refresh: bool = False) -> pd.DataFrame:
        cache_path = self.cache_dir / "company_tickers.json"
        payload = self._get_json(SEC_TICKERS_URL, cache_path, refresh=refresh)

        rows = []
        for value in payload.values():
            rows.append(
                {
                    "ticker": str(value["ticker"]).upper(),
                    "company_name": value["title"],
                    "cik": str(value["cik_str"]).zfill(10),
                }
            )
        return pd.DataFrame(rows).drop_duplicates(subset=["ticker"]).sort_values("ticker")

    def fetch_companyfacts(
        self,
        ticker: str,
        cik: str,
        as_of_date: date,
        refresh: bool = False,
    ) -> dict[str, Any]:
        cache_path = self.companyfacts_dir / f"{ticker}_{as_of_date.isoformat()}.json"
        url = SEC_COMPANYFACTS_URL.format(cik=str(cik).zfill(10))
        return self._get_json(url, cache_path, refresh=refresh)

    def _collect_facts(
        self,
        payload: dict[str, Any],
        taxonomy_name: str,
        concept_names: list[str],
        as_of_date: date,
    ) -> pd.DataFrame:
        taxonomy = payload.get("facts", {}).get(taxonomy_name, {})
        concept_rank = {concept: index for index, concept in enumerate(concept_names)}
        rows: list[dict[str, Any]] = []

        for concept in concept_names:
            concept_payload = taxonomy.get(concept)
            if not concept_payload:
                continue
            for unit, observations in concept_payload.get("units", {}).items():
                for observation in observations:
                    end_value = observation.get("end")
                    if not end_value:
                        continue
                    end_timestamp = pd.Timestamp(end_value)
                    if end_timestamp.date() > as_of_date:
                        continue
                    row = {
                        "concept": concept,
                        "concept_rank": concept_rank[concept],
                        "unit": unit,
                        "val": observation.get("val"),
                        "start": pd.Timestamp(observation["start"])
                        if observation.get("start")
                        else pd.NaT,
                        "end": end_timestamp,
                        "filed": pd.Timestamp(observation["filed"])
                        if observation.get("filed")
                        else pd.NaT,
                        "fy": observation.get("fy"),
                        "fp": observation.get("fp"),
                        "form": observation.get("form"),
                        "frame": observation.get("frame"),
                    }
                    rows.append(row)

        if not rows:
            return pd.DataFrame()

        frame = pd.DataFrame(rows)
        frame["val"] = pd.to_numeric(frame["val"], errors="coerce")
        frame = frame.dropna(subset=["val"])
        return frame

    @staticmethod
    def _annual_observations(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        annual_mask = (
            frame["form"].isin(ANNUAL_FORMS)
            | frame["fp"].eq("FY")
            | ((frame["end"] - frame["start"]).dt.days >= 330)
        )
        annual = frame.loc[annual_mask].copy()
        if annual.empty:
            return annual
        annual = annual.sort_values(
            by=["end", "filed", "concept_rank"],
            ascending=[False, False, True],
        )
        annual = annual.drop_duplicates(subset=["end"], keep="first")
        return annual.reset_index(drop=True)

    @staticmethod
    def _point_in_time_observations(frame: pd.DataFrame, annual_forms_only: bool = True) -> pd.DataFrame:
        if frame.empty:
            return frame
        filtered = frame.copy()
        if annual_forms_only:
            filtered = filtered.loc[filtered["form"].isin(ANNUAL_FORMS) | filtered["fp"].eq("FY")]
        filtered = filtered.sort_values(
            by=["end", "filed", "concept_rank"],
            ascending=[False, False, True],
        )
        filtered = filtered.drop_duplicates(subset=["end"], keep="first")
        return filtered.reset_index(drop=True)

    def _latest_value(
        self,
        payload: dict[str, Any],
        taxonomy_name: str,
        concept_names: list[str],
        as_of_date: date,
        annual: bool = False,
        annual_forms_only: bool = True,
    ) -> dict[str, Any] | None:
        frame = self._collect_facts(payload, taxonomy_name, concept_names, as_of_date)
        if frame.empty:
            return None
        selected = (
            self._annual_observations(frame)
            if annual
            else self._point_in_time_observations(frame, annual_forms_only=annual_forms_only)
        )
        if selected.empty:
            return None
        return selected.iloc[0].to_dict()

    def _latest_two_annual_values(
        self,
        payload: dict[str, Any],
        taxonomy_name: str,
        concept_names: list[str],
        as_of_date: date,
    ) -> list[dict[str, Any]]:
        frame = self._collect_facts(payload, taxonomy_name, concept_names, as_of_date)
        annual = self._annual_observations(frame)
        if annual.empty:
            return []
        return annual.head(2).to_dict(orient="records")

    def extract_company_metrics(
        self,
        ticker: str,
        cik: str,
        payload: dict[str, Any],
        as_of_date: date,
    ) -> dict[str, Any]:
        revenue_points = self._latest_two_annual_values(payload, "us-gaap", REVENUE_CONCEPTS, as_of_date)
        net_income = self._latest_value(payload, "us-gaap", NET_INCOME_CONCEPTS, as_of_date, annual=True)
        equity = self._latest_value(payload, "us-gaap", EQUITY_CONCEPTS, as_of_date)
        assets = self._latest_value(payload, "us-gaap", ASSET_CONCEPTS, as_of_date)
        shares = self._latest_value(payload, "dei", SHARE_CONCEPTS, as_of_date)
        if shares is None:
            shares = self._latest_value(
                payload,
                "us-gaap",
                SHARE_CONCEPTS,
                as_of_date,
                annual=False,
                annual_forms_only=False,
            )

        latest_revenue = revenue_points[0] if revenue_points else {}
        previous_revenue = revenue_points[1] if len(revenue_points) > 1 else {}
        revenue_value = latest_revenue.get("val")
        previous_revenue_value = previous_revenue.get("val")
        net_income_value = net_income.get("val") if net_income else None
        equity_value = equity.get("val") if equity else None
        shares_value = shares.get("val") if shares else None
        assets_value = assets.get("val") if assets else None

        revenue_growth = None
        if revenue_value and previous_revenue_value:
            revenue_growth = (revenue_value / previous_revenue_value) - 1

        net_margin = None
        if revenue_value and net_income_value:
            net_margin = net_income_value / revenue_value

        roe = None
        if equity_value and net_income_value:
            roe = net_income_value / equity_value

        return {
            "ticker": ticker,
            "cik": str(cik).zfill(10),
            "company_name": payload.get("entityName"),
            "fiscal_year": latest_revenue.get("fy") or (net_income.get("fy") if net_income else None),
            "period_end": latest_revenue.get("end") or (net_income.get("end") if net_income else None),
            "filing_date": latest_revenue.get("filed") or (net_income.get("filed") if net_income else None),
            "revenue": revenue_value,
            "previous_revenue": previous_revenue_value,
            "revenue_growth": revenue_growth,
            "net_income": net_income_value,
            "equity": equity_value,
            "assets": assets_value,
            "shares_outstanding": shares_value,
            "net_margin": net_margin,
            "roe": roe,
            "source": "SEC",
            "retrieved_at": utc_now_iso(),
            "as_of_date": as_of_date.isoformat(),
        }

    def build_fundamentals(
        self,
        tickers: list[str],
        as_of_date: date,
        refresh: bool = False,
    ) -> tuple[pd.DataFrame, list[dict[str, str]]]:
        ticker_map = self.fetch_ticker_map(refresh=refresh)
        ticker_lookup = ticker_map.set_index("ticker").to_dict(orient="index")

        rows: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []
        for ticker in tickers:
            lookup = ticker_lookup.get(ticker.upper())
            if not lookup:
                issues.append({"ticker": ticker, "issue": "Ticker not found in SEC mapping"})
                continue
            try:
                payload = self.fetch_companyfacts(
                    ticker=ticker.upper(),
                    cik=lookup["cik"],
                    as_of_date=as_of_date,
                    refresh=refresh,
                )
                rows.append(
                    self.extract_company_metrics(
                        ticker=ticker.upper(),
                        cik=lookup["cik"],
                        payload=payload,
                        as_of_date=as_of_date,
                    )
                )
                time.sleep(0.15)
            except Exception as exc:  # noqa: BLE001
                issues.append({"ticker": ticker, "issue": str(exc)})

        frame = pd.DataFrame(rows)
        if not frame.empty:
            frame["period_end"] = pd.to_datetime(frame["period_end"])
            frame["filing_date"] = pd.to_datetime(frame["filing_date"])
        return frame, issues
