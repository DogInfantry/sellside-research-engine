from __future__ import annotations

from datetime import date
from pathlib import Path

from trg_workbench.llm.reasoner import analyze_transcript
from trg_workbench.llm.transcript_fetcher import SECEarningsTranscriptFetcher


def build_management_commentary(
    tickers: list[str],
    as_of_date: date,
    fetch_live: bool = False,
    cache_dir: Path | None = None,
) -> list[dict[str, object]]:
    fetcher = SECEarningsTranscriptFetcher(cache_dir=cache_dir)
    rows: list[dict[str, object]] = []

    for ticker in tickers:
        document = (
            fetcher.fetch_latest(ticker, as_of_date=as_of_date)
            if fetch_live
            else fetcher.load_cached(ticker)
        )
        if document is None:
            continue
        analysis = analyze_transcript(ticker, document.text)
        if analysis is None:
            continue
        analysis["transcript_source_url"] = document.source_url
        analysis["transcript_filing_date"] = document.filing_date
        rows.append(analysis)

    return rows
