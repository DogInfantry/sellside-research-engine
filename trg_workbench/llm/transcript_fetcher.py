from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from trg_workbench.config import CACHE_DIR, SEC_USER_AGENT
from trg_workbench.io_utils import read_json, utc_now_iso, write_json
from trg_workbench.sources.sec import SECClient


SEC_FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"


@dataclass
class TranscriptDocument:
    ticker: str
    cik: str | None
    accession_number: str | None
    filing_date: str | None
    source_url: str | None
    text: str


class SECEarningsTranscriptFetcher:
    def __init__(
        self,
        cache_dir: Path | None = None,
        user_agent: str = SEC_USER_AGENT,
        session: requests.Session | None = None,
    ) -> None:
        self.cache_dir = cache_dir or CACHE_DIR / "transcripts"
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            }
        )

    def _text_cache_path(self, ticker: str) -> Path:
        return self.cache_dir / f"{ticker.upper()}_latest.txt"

    def _metadata_cache_path(self, ticker: str) -> Path:
        return self.cache_dir / f"{ticker.upper()}_latest.json"

    def load_cached(self, ticker: str) -> TranscriptDocument | None:
        text_path = self._text_cache_path(ticker)
        metadata_path = self._metadata_cache_path(ticker)
        if not text_path.exists():
            return None
        metadata = read_json(metadata_path) if metadata_path.exists() else {}
        return TranscriptDocument(
            ticker=ticker.upper(),
            cik=metadata.get("cik"),
            accession_number=metadata.get("accession_number"),
            filing_date=metadata.get("filing_date"),
            source_url=metadata.get("source_url"),
            text=text_path.read_text(encoding="utf-8"),
        )

    def fetch_latest(
        self,
        ticker: str,
        as_of_date: date,
        refresh: bool = False,
    ) -> TranscriptDocument | None:
        ticker = ticker.upper()
        cached = None if refresh else self.load_cached(ticker)
        if cached:
            return cached

        cik = self._lookup_cik(ticker)
        if not cik:
            return None

        hits = self._search_8k_hits(ticker, cik, as_of_date)
        for hit in hits:
            source_url = self._source_url(hit)
            if not source_url:
                continue
            response = self.session.get(source_url, timeout=30)
            response.raise_for_status()
            text = clean_filing_text(response.text)
            if not _looks_like_transcript(text):
                continue
            document = TranscriptDocument(
                ticker=ticker,
                cik=cik,
                accession_number=_hit_value(hit, "accessionNo", "adsh"),
                filing_date=_hit_value(hit, "file_date", "filedAt"),
                source_url=source_url,
                text=text,
            )
            self._write_cache(document)
            return document
        return None

    def _lookup_cik(self, ticker: str) -> str | None:
        ticker_map = SECClient(cache_dir=self.cache_dir.parent / "sec").fetch_ticker_map()
        row = ticker_map.loc[ticker_map["ticker"].eq(ticker.upper())]
        if row.empty:
            return None
        return str(row.iloc[0]["cik"]).zfill(10)

    def _search_8k_hits(self, ticker: str, cik: str, as_of_date: date) -> list[dict[str, Any]]:
        start_date = as_of_date - timedelta(days=540)
        params = {
            "q": f'"{ticker}" "earnings"',
            "dateRange": "custom",
            "startdt": start_date.isoformat(),
            "enddt": as_of_date.isoformat(),
            "forms": "8-K",
            "ciks": cik,
        }
        response = self.session.get(SEC_FULL_TEXT_SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        return hits if isinstance(hits, list) else []

    def _source_url(self, hit: dict[str, Any]) -> str | None:
        source = hit.get("_source", hit)
        for key in ["linkToHtml", "linkToFilingDetails"]:
            value = source.get(key)
            if isinstance(value, str) and value:
                return value if value.startswith("http") else f"https://www.sec.gov{value}"

        accession = _hit_value(hit, "accessionNo", "adsh")
        file_name = _hit_value(hit, "fileName", "file_name")
        cik = _hit_value(hit, "cik") or _first_cik(source.get("ciks"))
        if accession and file_name and cik:
            accession_dir = accession.replace("-", "")
            cik_dir = str(cik).lstrip("0")
            return f"https://www.sec.gov/Archives/edgar/data/{cik_dir}/{accession_dir}/{file_name}"
        return None

    def _write_cache(self, document: TranscriptDocument) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._text_cache_path(document.ticker).write_text(document.text, encoding="utf-8")
        write_json(
            self._metadata_cache_path(document.ticker),
            {
                "ticker": document.ticker,
                "cik": document.cik,
                "accession_number": document.accession_number,
                "filing_date": document.filing_date,
                "source_url": document.source_url,
                "retrieved_at": utc_now_iso(),
            },
        )


def clean_filing_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_transcript(text: str) -> bool:
    lower_text = text.lower()
    transcript_terms = ["earnings", "conference call", "question-and-answer", "q&a", "operator"]
    return sum(term in lower_text for term in transcript_terms) >= 2


def _hit_value(hit: dict[str, Any], *keys: str) -> str | None:
    source = hit.get("_source", hit)
    for key in keys:
        value = source.get(key)
        if value:
            return str(value)
    return None


def _first_cik(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str) and value:
        return value
    return None
