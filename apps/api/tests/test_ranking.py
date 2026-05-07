from datetime import datetime, timedelta, timezone

from app.core.models import MemoryEntry, MemoryType
from app.core.ranking import confidence_component, normalize_query, rank_memory, recency_component


def make_entry(
    *,
    title: str,
    context: str = "",
    confidence: float = 0.7,
    timestamp: str | None = None,
    tags: list[str] | None = None,
    memory_type: MemoryType = MemoryType.solution,
) -> MemoryEntry:
    return MemoryEntry(
        id=f"mem_{title.lower().replace(' ', '_')[:12]}",
        type=memory_type,
        title=title,
        context=context,
        resolution="",
        confidence=confidence,
        tags=tags or [],
        source="test",
        project="tests",
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
    )


def test_normalize_query_removes_stopwords_and_duplicates():
    assert normalize_query("how to fix SQLite SQLite in memory") == ["fix", "sqlite", "memory"]


def test_exact_title_match_beats_high_confidence_vague_memory():
    now = datetime.now(timezone.utc)
    exact = make_entry(
        title="Fix Stop hook capture",
        context="Stop hook stores assistant output.",
        confidence=0.6,
        timestamp=(now - timedelta(days=30)).isoformat(),
    )
    vague = make_entry(
        title="General implementation note",
        context="Implementation details were successful.",
        confidence=1.0,
        timestamp=now.isoformat(),
    )

    exact_score = rank_memory(exact, "Stop hook capture", now=now)
    vague_score = rank_memory(vague, "Stop hook capture", now=now)

    assert exact_score.matched is True
    assert vague_score.matched is False
    assert exact_score.score > vague_score.score


def test_recency_participates_in_hybrid_score():
    now = datetime.now(timezone.utc)
    fresh = make_entry(title="SQLite storage", timestamp=now.isoformat())
    stale = make_entry(title="SQLite storage", timestamp=(now - timedelta(days=365)).isoformat())

    assert rank_memory(fresh, "SQLite", now=now).score > rank_memory(stale, "SQLite", now=now).score


def test_importance_and_usage_participate_in_hybrid_score():
    base = make_entry(title="Ranking module", context="Hybrid scoring")
    important = make_entry(title="Ranking module", context="Hybrid scoring", tags=["ranking"])
    important.importance = 1.0
    important.retrieved_count = 10
    important.injected_count = 2

    assert rank_memory(important, "ranking").score > rank_memory(base, "ranking").score


def test_confidence_decays_with_age():
    now = datetime.now(timezone.utc)
    fresh = make_entry(title="Confidence decay", confidence=1.0, timestamp=now.isoformat())
    stale = make_entry(
        title="Confidence decay",
        confidence=1.0,
        timestamp=(now - timedelta(days=365)).isoformat(),
    )

    fresh_recency = recency_component(fresh.timestamp, now)
    stale_recency = recency_component(stale.timestamp, now)

    assert confidence_component(fresh, fresh_recency) > confidence_component(stale, stale_recency)
