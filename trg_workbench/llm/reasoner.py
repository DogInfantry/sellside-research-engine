from __future__ import annotations

from dataclasses import asdict, dataclass

from trg_workbench.llm.chunker import chunk_text, split_sentences
from trg_workbench.llm.retriever import retrieve_relevant_chunks


POSITIVE_TERMS = [
    "accelerate",
    "beat",
    "constructive",
    "demand",
    "expanded",
    "growth",
    "improved",
    "margin expansion",
    "raised",
    "record",
    "resilient",
    "strong",
    "upside",
]
NEGATIVE_TERMS = [
    "challenge",
    "decline",
    "delayed",
    "headwind",
    "lowered",
    "pressure",
    "risk",
    "slower",
    "soft",
    "uncertain",
    "weak",
]
GUIDANCE_TERMS = ["guidance", "outlook", "raised", "lowered", "reaffirmed", "expects", "forecast"]
RISK_TERMS = ["risk", "headwind", "pressure", "challenge", "uncertain", "weak", "decline", "slower"]
CATALYST_TERMS = ["launch", "buyback", "repurchase", "approval", "new product", "expansion", "partnership"]


@dataclass
class ManagementCommentary:
    ticker: str
    tone_score: float
    guidance_summary: str
    key_risks: list[str]
    catalyst_flags: list[str]
    analyst_qa_tone: str
    source: str = "heuristic_transcript_parser"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _term_count(text: str, terms: list[str]) -> int:
    lower_text = text.lower()
    return sum(lower_text.count(term) for term in terms)


def _tone_score(text: str) -> float:
    positive = _term_count(text, POSITIVE_TERMS)
    negative = _term_count(text, NEGATIVE_TERMS)
    if positive + negative == 0:
        return 0.5
    score = positive / (positive + negative)
    return round(min(max(score, 0.0), 1.0), 2)


def _tone_label(score: float) -> str:
    if score >= 0.60:
        return "constructive"
    if score <= 0.40:
        return "cautious"
    return "balanced"


def _matching_sentences(text: str, terms: list[str], limit: int) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for sentence in split_sentences(text):
        lower_sentence = sentence.lower()
        if any(term in lower_sentence for term in terms) and sentence not in seen:
            matches.append(sentence)
            seen.add(sentence)
        if len(matches) >= limit:
            break
    return matches


def _guidance_summary(text: str) -> str:
    matches = _matching_sentences(text, GUIDANCE_TERMS, limit=1)
    if matches:
        return matches[0]
    return "No explicit forward guidance language found in the available transcript excerpt."


def _qa_text(text: str) -> str:
    lower_text = text.lower()
    for marker in ["question-and-answer", "question and answer", "q&a", "analyst q"]:
        index = lower_text.find(marker)
        if index >= 0:
            return text[index:]
    return text


def analyze_transcript(ticker: str, transcript_text: str) -> dict[str, object] | None:
    chunks = chunk_text(transcript_text, max_words=500, overlap_words=50)
    if not chunks:
        return None

    relevant_chunks = retrieve_relevant_chunks(
        chunks,
        keywords=GUIDANCE_TERMS + RISK_TERMS + CATALYST_TERMS,
        limit=5,
    )
    relevant_text = " ".join(relevant_chunks)
    tone_score = _tone_score(relevant_text)
    qa_score = _tone_score(_qa_text(transcript_text))
    commentary = ManagementCommentary(
        ticker=ticker.upper(),
        tone_score=tone_score,
        guidance_summary=_guidance_summary(relevant_text),
        key_risks=_matching_sentences(relevant_text, RISK_TERMS, limit=3),
        catalyst_flags=_matching_sentences(relevant_text, CATALYST_TERMS, limit=3),
        analyst_qa_tone=_tone_label(qa_score),
    )
    return commentary.to_dict()
