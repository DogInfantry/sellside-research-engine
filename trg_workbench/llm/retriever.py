from __future__ import annotations


def retrieve_relevant_chunks(
    chunks: list[str],
    keywords: list[str],
    limit: int = 4,
) -> list[str]:
    if limit <= 0:
        return []

    normalized_keywords = [keyword.lower() for keyword in keywords]
    scored: list[tuple[int, int, str]] = []
    for index, chunk in enumerate(chunks):
        lower_chunk = chunk.lower()
        score = sum(lower_chunk.count(keyword) for keyword in normalized_keywords)
        scored.append((score, -index, chunk))

    matches = [item for item in scored if item[0] > 0]
    if not matches:
        return chunks[:limit]

    matches.sort(reverse=True)
    return [chunk for _, _, chunk in matches[:limit]]
