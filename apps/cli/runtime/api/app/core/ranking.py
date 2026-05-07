from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re

from app.core.models import MemoryEntry

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "co",
    "czy",
    "dla",
    "do",
    "i",
    "jak",
    "jest",
    "na",
    "oraz",
    "po",
    "w",
    "z",
    "ze",
}

EXACT_TOKEN_PATTERN = re.compile(r"[\w./\\:-]+")
FILE_OR_SYMBOL_PATTERN = re.compile(r"[./\\:-]|[A-Z][A-Za-z0-9_]*[A-Z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class RankedMemory:
    score: float
    matched: bool
    reason: str
    components: dict[str, float]


def normalize_query(query: str) -> list[str]:
    terms = []
    for term in EXACT_TOKEN_PATTERN.findall(query.lower()):
        value = term.strip(".,;!?()[]{}'\"`")
        if len(value) < 2 or value in STOPWORDS:
            continue
        if value not in terms:
            terms.append(value)
    return terms


def rank_memory(entry: MemoryEntry, query: str, now: datetime | None = None) -> RankedMemory:
    terms = normalize_query(query)
    text = searchable_text(entry)
    keyword_score, matched = keyword_component(text, entry.title.lower(), terms)
    exact_score = exact_component(entry, query)
    importance_score = 1.0 if entry.pinned else clamp(entry.importance)
    usage_score = usage_component(entry)
    recency_score = recency_component(entry.timestamp, now or datetime.now(timezone.utc))
    confidence_score = confidence_component(entry, recency_score)
    type_score = type_component(entry)
    tag_score = tag_component(entry, terms)

    if not terms:
        matched = True

    components = {
        "keyword": round(keyword_score * 4.0, 6),
        "exact": round(exact_score * 2.5, 6),
        "confidence": round(confidence_score * 1.2, 6),
        "importance": round(importance_score * 1.0, 6),
        "usage": round(usage_score * 0.7, 6),
        "recency": round(recency_score * 0.8, 6),
        "type": round(type_score * 0.4, 6),
        "tag": round(tag_score * 0.5, 6),
    }
    score = sum(components.values())
    return RankedMemory(
        score=round(score, 6),
        matched=matched or exact_score > 0,
        reason=ranking_reason(
            keyword_score=keyword_score,
            exact_score=exact_score,
            confidence_score=confidence_score,
            importance_score=importance_score,
            usage_score=usage_score,
            recency_score=recency_score,
            tag_score=tag_score,
            terms=terms,
            pinned=entry.pinned,
        ),
        components=components,
    )


def searchable_text(entry: MemoryEntry) -> str:
    return " ".join(
        [
            entry.title,
            entry.context,
            entry.resolution,
            " ".join(entry.file_paths),
            " ".join(entry.tags),
            entry.type.value,
            entry.source,
        ]
    ).lower()


def keyword_component(text: str, title: str, terms: list[str]) -> tuple[float, bool]:
    if not terms:
        return 0.0, True

    weighted_hits = 0.0
    for term in terms:
        if term in title:
            weighted_hits += 1.4
        elif term in text:
            weighted_hits += 1.0

    return weighted_hits / len(terms), weighted_hits > 0


def exact_component(entry: MemoryEntry, query: str) -> float:
    exact_terms = [term.lower() for term in EXACT_TOKEN_PATTERN.findall(query) if FILE_OR_SYMBOL_PATTERN.search(term)]
    if not exact_terms:
        return 0.0

    text = searchable_text(entry)
    hits = sum(1 for term in exact_terms if term in text)
    return hits / len(exact_terms)


def recency_component(timestamp: str, now: datetime) -> float:
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    age_days = max((now - parsed).total_seconds() / 86400, 0)
    return math.exp(-age_days / 90)


def confidence_component(entry: MemoryEntry, recency_score: float) -> float:
    return clamp(entry.confidence) * (0.5 + (recency_score * 0.5))


def usage_component(entry: MemoryEntry) -> float:
    total_uses = entry.retrieved_count + (entry.injected_count * 2)
    if total_uses <= 0:
        return 0.0
    return min(math.log1p(total_uses) / math.log1p(20), 1.0)


def type_component(entry: MemoryEntry) -> float:
    weights = {
        "solution": 1.0,
        "decision": 0.9,
        "pattern": 0.8,
        "bug": 0.7,
        "fact": 0.5,
    }
    return weights.get(entry.type.value, 0.5)


def tag_component(entry: MemoryEntry, terms: list[str]) -> float:
    if not terms or not entry.tags:
        return 0.0
    tags = {tag.lower() for tag in entry.tags}
    hits = sum(1 for term in terms if term in tags)
    return hits / len(terms)


def clamp(value: float) -> float:
    return max(0.0, min(value, 1.0))


def ranking_reason(
    *,
    keyword_score: float,
    exact_score: float,
    confidence_score: float,
    importance_score: float,
    usage_score: float,
    recency_score: float,
    tag_score: float,
    terms: list[str],
    pinned: bool,
) -> str:
    reasons = []
    if keyword_score > 0:
        reasons.append(f"matched query terms: {', '.join(terms)}")
    if exact_score > 0:
        reasons.append("matched exact file/symbol/command token")
    if tag_score > 0:
        reasons.append("matched tags")
    if pinned:
        reasons.append("manually pinned")
    elif importance_score >= 0.75:
        reasons.append("high importance")
    if confidence_score >= 0.75:
        reasons.append("high confidence")
    if usage_score > 0:
        reasons.append("previously reused")
    if recency_score >= 0.75:
        reasons.append("recent memory")
    if not reasons:
        reasons.append("included by default profile")
    return "; ".join(reasons)
