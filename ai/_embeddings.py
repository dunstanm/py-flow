"""
Embedding Providers — Provider-agnostic embedding API.

Usage::

    from ai._gemini import GeminiEmbeddings

    emb = GeminiEmbeddings(api_key="...", dimension=768)
    vectors = emb.embed(["hello world", "how are you"])
    query_vec = emb.embed_query("search query")
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts for document indexing.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (list of floats), one per input text.
        """
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """
        Embed a single search query.

        Some providers use different task types for queries vs documents
        to improve retrieval quality.

        Args:
            text: The search query text.

        Returns:
            Embedding vector (list of floats).
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Output embedding dimension."""
        ...
