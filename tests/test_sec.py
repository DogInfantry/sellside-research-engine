from datetime import date

from trg_workbench.sources.sec import SECClient


def test_extract_company_metrics_derives_growth_and_profitability():
    payload = {
        "entityName": "Goldman Sachs Group, Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 50_000_000_000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-20",
                            },
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 47_000_000_000,
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-15",
                            },
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 9_000_000_000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-20",
                            }
                        ]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {
                                "end": "2024-12-31",
                                "val": 120_000_000_000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-20",
                            }
                        ]
                    }
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "end": "2024-12-31",
                                "val": 300_000_000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-20",
                            }
                        ]
                    }
                }
            },
        },
    }

    client = SECClient()
    metrics = client.extract_company_metrics("GS", "0000886982", payload, date(2025, 3, 1))

    assert metrics["company_name"] == "Goldman Sachs Group, Inc."
    assert round(metrics["revenue_growth"], 4) == round((50_000_000_000 / 47_000_000_000) - 1, 4)
    assert round(metrics["net_margin"], 4) == round(9_000_000_000 / 50_000_000_000, 4)
    assert round(metrics["roe"], 4) == round(9_000_000_000 / 120_000_000_000, 4)

