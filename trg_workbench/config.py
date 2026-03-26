from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
NORMALIZED_DIR = DATA_DIR / "normalized"
LOGS_DIR = DATA_DIR / "logs"
OUTPUTS_DIR = ROOT_DIR / "outputs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
TEMPLATES_DIR = Path(__file__).resolve().parent / "reporting" / "templates"
ANALYST_VIEWS_PATH = DATA_DIR / "analyst_views.csv"

SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "TRGResearchWorkbench/1.0 (set SEC_USER_AGENT with contact details)",
)
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ECB_BASE_URL = "https://data-api.ecb.europa.eu/service/data"

DEFAULT_US_TICKERS = [
    "AAPL",
    "AMZN",
    "BAC",
    "BLK",
    "CAT",
    "CVX",
    "GE",
    "GOOGL",
    "GS",
    "HD",
    "JEF",
    "JPM",
    "LAZ",
    "META",
    "MS",
    "MSFT",
    "NVDA",
    "PJT",
    "PG",
    "UNH",
    "XOM",
]

US_SECTOR_PROXIES = {
    "XLC": "Communication Services",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLK": "Technology",
    "XLP": "Consumer Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
}

EUROPE_INDICES = {
    "^STOXX50E": "Euro Stoxx 50",
    "^FTSE": "FTSE 100",
    "^GDAXI": "DAX",
    "^FCHI": "CAC 40",
    "^IBEX": "IBEX 35",
}

ECB_SERIES = {
    "eurusd": {
        "dataset": "EXR",
        "series_key": "D.USD.EUR.SP00.A",
        "label": "EURUSD",
        "category": "fx",
        "display_name": "USD per EUR",
    },
    "gbpeur": {
        "dataset": "EXR",
        "series_key": "D.GBP.EUR.SP00.A",
        "label": "GBPEUR",
        "category": "fx",
        "display_name": "GBP per EUR",
    },
    "deposit_facility": {
        "dataset": "FM",
        "series_key": "D.U2.EUR.4F.KR.DFR.LEV",
        "label": "ECB_DFR",
        "category": "rates",
        "display_name": "ECB Deposit Facility Rate",
    },
    "main_refi": {
        "dataset": "FM",
        "series_key": "D.U2.EUR.4F.KR.MRR_RT.LEV",
        "label": "ECB_MRO",
        "category": "rates",
        "display_name": "ECB Main Refi Rate",
    },
}
