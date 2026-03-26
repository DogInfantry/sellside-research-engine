from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from trg_workbench.config import LOGS_DIR
from trg_workbench.io_utils import month_filter, read_json


EVENT_LOG_PATH = LOGS_DIR / "pipeline_events.jsonl"


def load_pipeline_events() -> pd.DataFrame:
    if not EVENT_LOG_PATH.exists():
        return pd.DataFrame()
    rows = []
    for line in EVENT_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame


def latest_manifest_for_month(month: str, normalized_dir: Path) -> dict[str, Any] | None:
    year, month_number = month.split("-")
    month_end = date(int(year), int(month_number), monthrange(int(year), int(month_number))[1])
    manifests = sorted(normalized_dir.glob("manifest_*.json"))
    candidates = []
    for path in manifests:
        try:
            manifest_date = date.fromisoformat(path.stem.replace("manifest_", ""))
        except ValueError:
            continue
        if manifest_date <= month_end:
            candidates.append((manifest_date, path))
    if not candidates:
        return None
    return read_json(candidates[-1][1])


def build_kpi_context(month: str, normalized_dir: Path) -> dict[str, Any]:
    events = load_pipeline_events()
    monthly_events = month_filter(events, "timestamp", month) if not events.empty else pd.DataFrame()
    report_events = (
        monthly_events.loc[monthly_events["event_type"] == "report_generated"].copy()
        if not monthly_events.empty
        else pd.DataFrame()
    )
    fetch_events = (
        monthly_events.loc[monthly_events["event_type"] == "fetch_source"].copy()
        if not monthly_events.empty
        else pd.DataFrame()
    )
    manifest = latest_manifest_for_month(month, normalized_dir)

    summary = {
        "month": month,
        "report_count": int(len(report_events)),
        "fetch_count": int(len(fetch_events)),
        "sources_seen": sorted(fetch_events["source"].dropna().unique().tolist()) if not fetch_events.empty else [],
        "latest_manifest_date": manifest.get("as_of_date") if manifest else None,
        "coverage": manifest.get("coverage", {}) if manifest else {},
    }

    report_mix = (
        report_events.groupby("report_type")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        if not report_events.empty
        else pd.DataFrame(columns=["report_type", "count"])
    )
    fetch_by_source = (
        fetch_events.groupby("source")["rows"]
        .sum()
        .reset_index()
        .sort_values("rows", ascending=False)
        if not fetch_events.empty
        else pd.DataFrame(columns=["source", "rows"])
    )
    report_cadence = (
        report_events.assign(day=report_events["timestamp"].dt.date.astype(str))
        .groupby(["day", "report_type"])
        .size()
        .reset_index(name="count")
        .sort_values("day")
        if not report_events.empty
        else pd.DataFrame(columns=["day", "report_type", "count"])
    )
    source_freshness = pd.DataFrame(columns=["source", "last_timestamp"])
    if not fetch_events.empty:
        latest_fetches = fetch_events.sort_values("timestamp").groupby("source").tail(1)
        source_freshness = latest_fetches[["source", "timestamp"]].rename(
            columns={"timestamp": "last_timestamp"}
        )

    return {
        "summary": summary,
        "report_mix": report_mix,
        "fetch_by_source": fetch_by_source,
        "report_cadence": report_cadence,
        "source_freshness": source_freshness,
        "manifest": manifest or {},
    }

