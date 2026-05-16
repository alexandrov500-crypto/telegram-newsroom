from __future__ import annotations

import asyncio

from editorial.similarity import LexicalJaccardSimilarity, jaccard_tokens


def test_jaccard_tokens_basic() -> None:
    assert jaccard_tokens("hello world", "hello there") > 0.2


def test_lexical_backend_async() -> None:
    async def run() -> float:
        b = LexicalJaccardSimilarity()
        return await b.similarity("alpha beta gamma", "alpha beta delta")

    assert asyncio.run(run()) > 0.2
