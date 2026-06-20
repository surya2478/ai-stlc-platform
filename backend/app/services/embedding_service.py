"""
EmbeddingService — provider-agnostic text embedding for RAG.

Supports three providers:
  - sentence_transformers: local model (recommended default)
  - openai: OpenAI Embeddings API (requires OPENAI_API_KEY)
  - huggingface: HuggingFace Inference API (requires HUGGINGFACE_API_KEY)

Usage:
    svc = EmbeddingService()
    result = svc.embed(["text one", "text two"])
    # result.vectors: list[list[float]]
    # result.model: str
    # result.dimension: int
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimension: int


def _chunk_hash(text: str) -> str:
    """SHA-256 hex digest of normalised chunk text (for dedup)."""
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


class EmbeddingService:
    """
    Generates text embeddings using the configured provider.

    Instantiating this class is cheap — model loading is deferred to the
    first embed() call and cached on the instance.
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ) -> None:
        self._provider = provider or settings.embedding_provider
        self._model_name = model or settings.embedding_model
        self._dimension = dimension or settings.embedding_dimension
        self._batch_size = settings.embedding_batch_size
        self._model = None  # lazy-loaded

    # ── public API ────────────────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a list of texts, returning vectors in the same order."""
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model_name, dimension=self._dimension)

        texts = [self._normalise(t) for t in texts]
        self._validate_input(texts)

        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_vecs = self._embed_batch(batch)
            vectors.extend(batch_vecs)

        self._validate_dimensions(vectors)
        return EmbeddingResult(vectors=vectors, model=self._model_name, dimension=self._dimension)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        result = self.embed([text])
        return result.vectors[0]

    @staticmethod
    def chunk_hash(text: str) -> str:
        return _chunk_hash(text)

    # ── internal ──────────────────────────────────────────────────────────────

    def _normalise(self, text: str) -> str:
        return " ".join(text.split())[:8192]  # guard against runaway inputs

    def _validate_input(self, texts: list[str]) -> None:
        for i, t in enumerate(texts):
            if not t:
                raise ValueError(f"Empty text at index {i} — cannot embed empty strings.")

    def _validate_dimensions(self, vectors: list[list[float]]) -> None:
        for i, v in enumerate(vectors):
            if len(v) != self._dimension:
                raise ValueError(
                    f"Embedding dimension mismatch at index {i}: "
                    f"expected {self._dimension}, got {len(v)}. "
                    f"Check EMBEDDING_MODEL and EMBEDDING_DIMENSION settings."
                )

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._provider == "sentence_transformers":
            return self._embed_sentence_transformers(texts)
        elif self._provider == "openai":
            return self._embed_openai(texts)
        elif self._provider == "huggingface":
            return self._embed_huggingface(texts)
        else:
            raise ValueError(f"Unknown embedding provider: {self._provider!r}")

    # ── provider implementations ──────────────────────────────────────────────

    def _embed_sentence_transformers(self, texts: list[str]) -> list[list[float]]:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Add it to backend requirements to use the sentence_transformers embedding provider."
            )

        if self._model is None:
            logger.info("Loading sentence-transformers model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)

        embeddings = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [e.tolist() for e in embeddings]

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package is not installed.")

        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        response = client.embeddings.create(input=texts, model=self._model_name)
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    def _embed_huggingface(self, texts: list[str]) -> list[list[float]]:
        import json
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx package is not installed.")

        api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self._model_name}"
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
        response = httpx.post(api_url, headers=headers, json={"inputs": texts}, timeout=30)
        response.raise_for_status()
        return response.json()


# Module-level singleton — avoids reloading the model on every request
_service_instance: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Return the module-level singleton EmbeddingService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EmbeddingService()
    return _service_instance
