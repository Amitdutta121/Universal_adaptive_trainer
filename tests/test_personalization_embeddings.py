"""Embedding helpers for personalization review-example retrieval."""

from __future__ import annotations

import pytest

from app.personalization.embeddings import FakeEmbedder, cosine_similarity, example_content_hash


def test_cosine_identical_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_fake_embedder_is_deterministic() -> None:
    emb = FakeEmbedder(dim=8)
    a = emb.embed(["hello"])[0]
    b = emb.embed(["hello"])[0]
    assert a == b
    assert emb.embed(["hello"])[0] != emb.embed(["world"])[0]


def test_content_hash_stable() -> None:
    assert example_content_hash("x") == example_content_hash("x")
