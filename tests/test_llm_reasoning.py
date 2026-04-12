from datetime import date
from pathlib import Path
import shutil

from trg_workbench.llm.chunker import chunk_text
from trg_workbench.llm.pipeline import build_management_commentary
from trg_workbench.llm.reasoner import analyze_transcript
from trg_workbench.llm.retriever import retrieve_relevant_chunks
from trg_workbench.llm.transcript_fetcher import clean_filing_text


def _fixture_text() -> str:
    return Path("tests/fixtures/sample_earnings_transcript.txt").read_text(encoding="utf-8")


def test_chunker_preserves_overlap_between_chunks():
    text = " ".join(f"Sentence {index} has enough words for chunking." for index in range(20))
    chunks = chunk_text(text, max_words=25, overlap_words=5)

    assert len(chunks) > 1
    assert chunks[0].split()[-5:] == chunks[1].split()[:5]


def test_retriever_prioritizes_keyword_chunks():
    chunks = [
        "Macro data stayed quiet.",
        "Management raised guidance and discussed demand.",
        "Closing remarks were short.",
    ]

    assert retrieve_relevant_chunks(chunks, ["guidance"], limit=1) == [chunks[1]]


def test_clean_filing_text_strips_html_markup():
    raw_html = "<html><script>ignore()</script><body><p>Operator &amp; management remarks.</p></body></html>"

    assert clean_filing_text(raw_html) == "Operator & management remarks."


def test_analyze_transcript_extracts_management_commentary():
    result = analyze_transcript("AAA", _fixture_text())

    assert result is not None
    assert result["ticker"] == "AAA"
    assert result["tone_score"] > 0.5
    assert "raised full-year revenue guidance" in result["guidance_summary"]
    assert result["key_risks"]
    assert result["catalyst_flags"]
    assert result["analyst_qa_tone"] == "constructive"


def test_management_commentary_uses_cached_transcript_without_live_fetch():
    cache_dir = Path("data/cache/test_transcripts")
    shutil.rmtree(cache_dir, ignore_errors=True)
    try:
        cache_dir.mkdir(parents=True)
        (cache_dir / "AAA_latest.txt").write_text(_fixture_text(), encoding="utf-8")

        rows = build_management_commentary(["AAA"], date(2026, 3, 27), cache_dir=cache_dir)

        assert rows
        assert rows[0]["ticker"] == "AAA"
        assert rows[0]["transcript_source_url"] is None
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)
