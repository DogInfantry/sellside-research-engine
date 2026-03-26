from datetime import date

import pandas as pd

from trg_workbench.sources.ecb import ECBClient


def test_standardize_frame_normalizes_columns():
    raw = pd.DataFrame(
        {
            "TIME_PERIOD": ["2026-03-24", "2026-03-25"],
            "OBS_VALUE": ["1.082", "1.091"],
        }
    )

    normalized = ECBClient._standardize_frame(
        raw,
        label="EURUSD",
        display_name="USD per EUR",
        category="fx",
        as_of_date=date(2026, 3, 25),
    )

    assert list(normalized.columns[:4]) == ["date", "value", "label", "display_name"]
    assert normalized["value"].iloc[-1] == 1.091
    assert normalized["category"].iloc[0] == "fx"

