import json
import shutil
from pathlib import Path

from trg_workbench.analytics import kpis


def test_build_kpi_context_aggregates_events(monkeypatch):
    base_dir = Path("tests_runtime_kpis")
    shutil.rmtree(base_dir, ignore_errors=True)
    base_dir.mkdir(exist_ok=True)
    log_path = base_dir / "pipeline_events.jsonl"
    events = [
        {
            "timestamp": "2026-03-26T08:00:00+00:00",
            "event_type": "fetch_source",
            "source": "SEC",
            "rows": 20,
        },
        {
            "timestamp": "2026-03-26T08:10:00+00:00",
            "event_type": "report_generated",
            "report_type": "daily",
            "rows": 10,
        },
    ]
    log_path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")

    normalized_dir = base_dir / "normalized"
    normalized_dir.mkdir(exist_ok=True)
    manifest_path = normalized_dir / "manifest_2026-03-26.json"
    manifest_path.write_text(
        json.dumps(
            {
                "as_of_date": "2026-03-26",
                "coverage": {"us_equities": 20, "macro_series": 4},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(kpis, "EVENT_LOG_PATH", log_path)
    context = kpis.build_kpi_context("2026-03", normalized_dir)

    assert context["summary"]["report_count"] == 1
    assert context["summary"]["fetch_count"] == 1
    assert context["summary"]["coverage"]["us_equities"] == 20
    shutil.rmtree(base_dir, ignore_errors=True)
