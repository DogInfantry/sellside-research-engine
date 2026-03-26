from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import pandas as pd
from jinja2.runtime import Undefined


def as_timestamp(value: date | datetime | str) -> pd.Timestamp:
    if isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value)


def pct(value: float | None, decimals: int = 1) -> str:
    if isinstance(value, Undefined):
        return "n/a"
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value * 100:.{decimals}f}%"


def number(value: float | int | None, decimals: int = 1) -> str:
    if isinstance(value, Undefined):
        return "n/a"
    if value is None or pd.isna(value):
        return "n/a"
    magnitude = abs(float(value))
    if magnitude >= 1_000_000_000:
        return f"{value / 1_000_000_000:.{decimals}f}B"
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.{decimals}f}M"
    if magnitude >= 1_000:
        return f"{value / 1_000:.{decimals}f}K"
    return f"{value:.{decimals}f}"


def bps_from_pct_change(value: float | None) -> str:
    if isinstance(value, Undefined):
        return "n/a"
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value * 100:.0f} bps"


def safe_mean(values: Iterable[float]) -> float | None:
    series = pd.Series(list(values), dtype="float64").dropna()
    if series.empty:
        return None
    return float(series.mean())


def flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame
    flattened = frame.copy()
    flattened.columns = [
        "_".join(str(level) for level in column if level not in ("", None)).strip("_")
        for column in flattened.columns
    ]
    return flattened
