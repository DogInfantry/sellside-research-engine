from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from trg_workbench.config import CACHE_DIR, CHARTS_DIR, LOGS_DIR, NORMALIZED_DIR, OUTPUTS_DIR


DATE_SUFFIX_RE = re.compile(r"(?P<prefix>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.(?P<ext>csv|json)$")


def ensure_directories() -> None:
    directories = [
        CACHE_DIR,
        CACHE_DIR / "sec",
        CACHE_DIR / "sec" / "companyfacts",
        CACHE_DIR / "ecb",
        CACHE_DIR / "market",
        NORMALIZED_DIR,
        LOGS_DIR,
        OUTPUTS_DIR,
        CHARTS_DIR,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_dataframe(path: Path, parse_dates: list[str] | None = None) -> pd.DataFrame:
    try:
        return pd.read_csv(path, parse_dates=parse_dates)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def resolve_dated_file(directory: Path, prefix: str, target_date: date, extension: str = "csv") -> Path:
    candidates: list[tuple[date, Path]] = []
    for path in directory.glob(f"{prefix}_*.{extension}"):
        match = DATE_SUFFIX_RE.match(path.name)
        if not match:
            continue
        file_date = date.fromisoformat(match.group("date"))
        if file_date <= target_date:
            candidates.append((file_date, path))
    if not candidates:
        raise FileNotFoundError(
            f"No {prefix} dataset found on or before {target_date.isoformat()} in {directory}."
        )
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def resolve_manifest(target_date: date) -> Path:
    return resolve_dated_file(NORMALIZED_DIR, "manifest", target_date, extension="json")


def month_filter(frame: pd.DataFrame, column: str, month: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    start = pd.Timestamp(f"{month}-01")
    end = start + pd.offsets.MonthEnd(1)
    series = pd.to_datetime(frame[column])
    tz = getattr(series.dt, "tz", None)
    if tz is not None:
        start = start.tz_localize(tz)
        end = end.tz_localize(tz)
    return frame[(series >= start) & (series <= end)]
