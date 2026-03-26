from __future__ import annotations

import io
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from trg_workbench.config import CACHE_DIR, ECB_BASE_URL, ECB_SERIES
from trg_workbench.io_utils import utc_now_iso


class ECBClient:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR / "ecb"
        self.session = requests.Session()
        self.session.headers.update({"Accept": "text/csv"})

    def _fetch_csv(self, url: str, cache_path: Path, params: dict[str, str], refresh: bool = False) -> pd.DataFrame:
        if cache_path.exists() and not refresh:
            return pd.read_csv(cache_path)

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                frame = pd.read_csv(io.StringIO(response.text))
                frame.to_csv(cache_path, index=False)
                return frame
            except (requests.RequestException, pd.errors.ParserError) as exc:
                last_error = exc
                time.sleep((attempt + 1) * 1.5)
        raise RuntimeError(f"ECB request failed for {url}") from last_error

    @staticmethod
    def _standardize_frame(frame: pd.DataFrame, label: str, display_name: str, category: str, as_of_date: date) -> pd.DataFrame:
        normalized = frame.copy()
        normalized.columns = [str(column).strip().lower() for column in normalized.columns]
        if "time_period" not in normalized.columns or "obs_value" not in normalized.columns:
            raise ValueError("Unexpected ECB response shape; TIME_PERIOD and OBS_VALUE columns are required.")

        normalized = normalized[["time_period", "obs_value"]].rename(
            columns={"time_period": "date", "obs_value": "value"}
        )
        normalized["date"] = pd.to_datetime(normalized["date"])
        normalized["value"] = pd.to_numeric(normalized["value"], errors="coerce")
        normalized["label"] = label
        normalized["display_name"] = display_name
        normalized["category"] = category
        normalized["source"] = "ECB"
        normalized["retrieved_at"] = utc_now_iso()
        normalized["as_of_date"] = as_of_date.isoformat()
        return normalized.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)

    def fetch_series(
        self,
        dataset: str,
        series_key: str,
        label: str,
        display_name: str,
        category: str,
        start_date: date,
        end_date: date,
        refresh: bool = False,
    ) -> pd.DataFrame:
        url = f"{ECB_BASE_URL}/{dataset}/{series_key}"
        cache_path = self.cache_dir / f"{label}_{end_date.isoformat()}.csv"
        raw = self._fetch_csv(
            url=url,
            cache_path=cache_path,
            params={
                "startPeriod": start_date.isoformat(),
                "endPeriod": end_date.isoformat(),
                "format": "csvdata",
            },
            refresh=refresh,
        )
        return self._standardize_frame(raw, label, display_name, category, end_date)

    def build_macro_dataset(self, as_of_date: date, refresh: bool = False) -> tuple[pd.DataFrame, list[str]]:
        start_date = as_of_date - timedelta(days=370)
        frames: list[pd.DataFrame] = []
        issues: list[str] = []
        for spec in ECB_SERIES.values():
            try:
                frames.append(
                    self.fetch_series(
                        dataset=spec["dataset"],
                        series_key=spec["series_key"],
                        label=spec["label"],
                        display_name=spec["display_name"],
                        category=spec["category"],
                        start_date=start_date,
                        end_date=as_of_date,
                        refresh=refresh,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                issues.append(f"{spec['label']}: {exc}")
        if not frames:
            return pd.DataFrame(), issues
        combined = pd.concat(frames, ignore_index=True)
        return combined.sort_values(["label", "date"]).reset_index(drop=True), issues
