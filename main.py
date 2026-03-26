from __future__ import annotations

import argparse
from datetime import date

from trg_workbench.pipeline import (
    build_all,
    build_daily_report,
    build_kpi_report,
    build_weekly_report,
    fetch_data,
)


def valid_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected YYYY-MM-DD date, received {value!r}."
        ) from exc


def valid_month(value: str) -> str:
    try:
        year, month = value.split("-")
        date(int(year), int(month), 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected YYYY-MM month, received {value!r}."
        ) from exc
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Real-data Tactical Research Group workbench."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_cmd = subparsers.add_parser(
        "fetch-data",
        help="Download and normalize SEC, ECB, and Yahoo Finance data.",
    )
    fetch_cmd.add_argument("--as-of", required=True, type=valid_date)

    daily_cmd = subparsers.add_parser(
        "build-daily",
        help="Generate the daily tactical note.",
    )
    daily_cmd.add_argument("--date", required=True, type=valid_date)

    weekly_cmd = subparsers.add_parser(
        "build-weekly",
        help="Generate the weekly research wrap.",
    )
    weekly_cmd.add_argument("--week-ending", required=True, type=valid_date)

    kpi_cmd = subparsers.add_parser(
        "build-kpis",
        help="Generate the management KPI report.",
    )
    kpi_cmd.add_argument("--month", required=True, type=valid_month)

    all_cmd = subparsers.add_parser(
        "build-all",
        help="Fetch data and generate all reports for an as-of date.",
    )
    all_cmd.add_argument("--as-of", required=True, type=valid_date)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch-data":
        fetch_data(args.as_of)
    elif args.command == "build-daily":
        build_daily_report(args.date)
    elif args.command == "build-weekly":
        build_weekly_report(args.week_ending)
    elif args.command == "build-kpis":
        build_kpi_report(args.month)
    elif args.command == "build-all":
        build_all(args.as_of)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

