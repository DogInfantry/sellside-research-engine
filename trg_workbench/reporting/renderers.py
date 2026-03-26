from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from trg_workbench.config import CHARTS_DIR, TEMPLATES_DIR
from trg_workbench.io_utils import ensure_directories
from trg_workbench.utils import bps_from_pct_change, number, pct


matplotlib.use("Agg")
import matplotlib.pyplot as plt


def build_environment() -> Environment:
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["pct"] = pct
    environment.filters["number"] = number
    environment.filters["bps"] = bps_from_pct_change
    return environment


def render_template(template_name: str, context: dict[str, Any]) -> str:
    environment = build_environment()
    template = environment.get_template(template_name)
    return template.render(**context)


def write_report(path: Path, content: str) -> Path:
    ensure_directories()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def plot_bar(frame: pd.DataFrame, x: str, y: str, title: str, path: Path) -> Path:
    ensure_directories()
    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(frame[x], frame[y], color="#1f4e79")
    axis.set_title(title)
    axis.tick_params(axis="x", rotation=30)
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_line(frame: pd.DataFrame, x: str, y: str, title: str, path: Path, hue: str | None = None) -> Path:
    ensure_directories()
    fig, axis = plt.subplots(figsize=(8, 4.5))
    if hue and hue in frame.columns:
        for label, group in frame.groupby(hue):
            axis.plot(group[x], group[y], marker="o", label=label)
        axis.legend()
    else:
        axis.plot(frame[x], frame[y], marker="o")
    axis.set_title(title)
    axis.tick_params(axis="x", rotation=30)
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def build_kpi_charts(context: dict[str, Any]) -> dict[str, str]:
    charts: dict[str, str] = {}
    report_mix = context["report_mix"]
    fetch_by_source = context["fetch_by_source"]
    report_cadence = context["report_cadence"]
    month = context["summary"]["month"].replace("-", "_")

    if not report_mix.empty:
        chart_path = CHARTS_DIR / f"report_mix_{month}.png"
        plot_bar(report_mix, "report_type", "count", "Report Mix", chart_path)
        charts["report_mix"] = chart_path.name

    if not fetch_by_source.empty:
        chart_path = CHARTS_DIR / f"fetch_by_source_{month}.png"
        plot_bar(fetch_by_source, "source", "rows", "Rows Fetched by Source", chart_path)
        charts["fetch_by_source"] = chart_path.name

    if not report_cadence.empty:
        chart_path = CHARTS_DIR / f"report_cadence_{month}.png"
        plot_line(report_cadence, "day", "count", "Report Cadence", chart_path, hue="report_type")
        charts["report_cadence"] = chart_path.name

    return charts
