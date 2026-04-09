"""
main_v2.py — Enhanced CLI for TRG Research Workbench v2.

New commands:
  build-report   Full research note (HTML + PDF + Markdown + charts)
  fetch-all      Fetch all data sources including US macro

Original commands still work via main.py.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _validate_date(s: str) -> str:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format '{s}'. Use YYYY-MM-DD.")


# DRY RUN FUNCTION
def run_dry_run_checks(args) -> int:
    import os

    checks_passed = True
    print("\nRunning dry-run checks...\n")

    # Date check
    try:
        datetime.strptime(args.as_of, "%Y-%m-%d")
        print("✓ Date parsed")
    except Exception:
        print("✗ Invalid date format")
        checks_passed = False

    # SEC_USER_AGENT
    if os.getenv("SEC_USER_AGENT"):
        print("✓ SEC user agent set")
    else:
        print("✗ SEC_USER_AGENT missing")
        checks_passed = False

    # Output directory
    if os.path.exists("outputs") and os.access("outputs", os.W_OK):
        print("✓ Output directory writable")
    else:
        print("✗ Output directory issue")
        checks_passed = False

    # WeasyPrint dependency
    try:
        import weasyprint  # noqa
        print("✓ WeasyPrint available")
    except Exception:
        print("✗ WeasyPrint / PDF dependencies missing")
        checks_passed = False

    print("\nDry run complete.")
    return 0 if checks_passed else 1


def cmd_fetch_all(args: argparse.Namespace) -> int:
    if args.dry_run:
        return run_dry_run_checks(args)

    from trg_workbench.pipeline_v2 import fetch_data_v2
    result = fetch_data_v2(args.as_of)

    print(f"[OK] All data fetched for {args.as_of}")
    if "us_macro_snapshot" in result:
        print(f"  US macro: {len(result['us_macro_snapshot'])} series")
    return 0


def cmd_build_report(args: argparse.Namespace) -> int:
    if args.dry_run:
        return run_dry_run_checks(args)

    from trg_workbench.pipeline_v2 import build_research_report_v2

    formats = args.formats.split(",") if args.formats else ["html", "pdf", "markdown"]
    print(f"Building research report for {args.as_of} | formats: {formats}")

    outputs = build_research_report_v2(args.as_of, output_formats=formats)
    if not outputs:
        print("ERROR: Report generation failed. Run fetch-all first.", file=sys.stderr)
        return 1

    print(f"\n[DONE] Report generation complete ({len(outputs)} files):")
    for fmt, path in outputs.items():
        print(f"  [{fmt.upper()}] {path}")

    return 0


def cmd_build_all_v2(args: argparse.Namespace) -> int:
    if args.dry_run:
        return run_dry_run_checks(args)

    print(f"Running full v2 pipeline for {args.as_of}...")
    rc = cmd_fetch_all(args)
    if rc != 0:
        return rc
    return cmd_build_report(args)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="trg-v2",
        description="TRG Research Workbench v2 — Sell-Side Research Engine",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # fetch-all
    p_fetch = sub.add_parser("fetch-all")
    p_fetch.add_argument("--as-of", type=_validate_date, default=datetime.today().strftime("%Y-%m-%d"))
    p_fetch.add_argument("--dry-run", action="store_true", help="Run validation only")
    p_fetch.set_defaults(func=cmd_fetch_all)

    # build-report
    p_report = sub.add_parser("build-report")
    p_report.add_argument("--as-of", type=_validate_date, default=datetime.today().strftime("%Y-%m-%d"))
    p_report.add_argument("--formats", type=str, default="html,pdf,markdown")
    p_report.add_argument("--dry-run", action="store_true", help="Run validation only")
    p_report.set_defaults(func=cmd_build_report)

    # build-all
    p_all = sub.add_parser("build-all")
    p_all.add_argument("--as-of", type=_validate_date, default=datetime.today().strftime("%Y-%m-%d"))
    p_all.add_argument("--formats", type=str, default="html,pdf,markdown")
    p_all.add_argument("--dry-run", action="store_true", help="Run validation only")
    p_all.set_defaults(func=cmd_build_all_v2)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())