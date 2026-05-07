from __future__ import annotations

from collections import Counter
from hashlib import blake2b
import math
import re

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_./:-]+")
DIMENSIONS = 64

SYNONYMS = {
    "bug": ["error", "failure", "fault"],
    "bugs": ["error", "failure", "fault"],
    "error": ["bug", "failure", "fault"],
    "errors": ["bug", "failure", "fault"],
    "failure": ["bug", "error", "fault"],
    "failures": ["bug", "error", "fault"],
    "fix": ["solution", "repair", "resolve"],
    "fixed": ["solution", "repair", "resolved"],
    "solution": ["fix", "resolve", "repair"],
    "capture": ["extract", "store", "record"],
    "captured": ["extract", "store", "record"],
    "extract": ["capture", "store", "record"],
    "history": ["audit", "version", "timeline"],
    "audit": ["history", "version", "timeline"],
    "ranking": ["retrieval", "search", "score"],
    "retrieval": ["ranking", "search", "score"],
    "secret": ["token", "credential", "password"],
    "secrets": ["token", "credential", "password"],
}


def embed_text(text: str) -> list[float]:
    counts: Counter[int] = Counter()
    for token in _tokens(text):
        _add_token(counts, token, 1.0)
        for synonym in SYNONYMS.get(token, []):
            _add_token(counts, synonym, 0.45)

    if not counts:
        return [0.0] * DIMENSIONS

    vector = [0.0] * DIMENSIONS
    for index, weight in counts.items():
        vector[index] = weight

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False))


def _tokens(text: str) -> list[str]:
    tokens = []
    for token in TOKEN_PATTERN.findall(text.lower()):
        value = token.strip(".,;!?()[]{}'\"`")
        if len(value) >= 2:
            tokens.append(value)
    return tokens


def _add_token(counts: Counter[int], token: str, weight: float) -> None:
    digest = blake2b(token.encode("utf-8"), digest_size=4).digest()
    index = int.from_bytes(digest, "big") % DIMENSIONS
    counts[index] += weight
