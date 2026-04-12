from __future__ import annotations

import re


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []
    return [sentence.strip() for sentence in SENTENCE_RE.split(normalized) if sentence.strip()]


def _word_chunks(words: list[str], max_words: int, overlap_words: int) -> list[str]:
    chunks: list[str] = []
    step = max(1, max_words - overlap_words)
    for start in range(0, len(words), step):
        chunk_words = words[start : start + max_words]
        if chunk_words:
            chunks.append(" ".join(chunk_words))
    return chunks


def chunk_text(text: str, max_words: int = 500, overlap_words: int = 50) -> list[str]:
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if overlap_words < 0:
        raise ValueError("overlap_words cannot be negative")
    if overlap_words >= max_words:
        raise ValueError("overlap_words must be smaller than max_words")

    chunks: list[str] = []
    current: list[str] = []
    current_count = 0

    for sentence in split_sentences(text):
        words = sentence.split()
        if len(words) > max_words:
            if current:
                chunks.append(" ".join(current))
                current = current[-overlap_words:] if overlap_words else []
                current_count = len(current)
            chunks.extend(_word_chunks(words, max_words, overlap_words))
            continue

        if current and current_count + len(words) > max_words:
            chunks.append(" ".join(current))
            current = current[-overlap_words:] if overlap_words else []
            current_count = len(current)

        current.extend(words)
        current_count += len(words)

    if current:
        chunks.append(" ".join(current))

    return chunks
