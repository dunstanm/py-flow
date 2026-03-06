"""
Gemini provider implementations — Google Gemini via google-genai SDK.

Contains:
  - GeminiLLM: LLM provider for text generation, streaming, and tool calling
  - GeminiEmbeddings: Embedding provider for retrieval and semantic search

All google.genai imports are lazy-loaded at first use.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Generator
from typing import Any, TypeVar, cast

from google import genai
from google.genai import types

from ai._embeddings import EmbeddingProvider
from ai._llm import LLMClient
from ai._types import LLMResponse, Message, ToolCall

_T = TypeVar("_T")

logger = logging.getLogger(__name__)


# ── GeminiLLM ────────────────────────────────────────────────────────────


class GeminiLLM(LLMClient):
    """
    Google Gemini LLM provider via the google-genai SDK.

    Supports text generation, conversation history, streaming,
    and tool/function calling.

    Args:
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        model: Model name (default: gemini-3-flash-preview).
        max_retries: Retry attempts on transient errors (default: 3).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3-flash-preview",
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Gemini API key required. Pass api_key= or set GEMINI_API_KEY env var."
            )
        self._model = model
        self._max_retries = max_retries
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """Lazy-init the genai client."""
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    @property
    def model_name(self) -> str:
        return self._model

    def generate(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a response using Gemini."""

        client = self._get_client()
        contents = self._messages_to_contents(messages)
        config = self._build_config(tools, temperature, max_tokens)

        result = self._call_with_retry(
            lambda: client.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
        )

        return self._parse_response(result)

    def stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """Stream response chunks from Gemini."""

        client = self._get_client()
        contents = self._messages_to_contents(messages)
        config = self._build_config(tools, temperature, max_tokens)

        response_stream = client.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )

        for chunk in response_stream:
            if chunk.text:
                yield chunk.text

    # ── Internal helpers ─────────────────────────────────────────────────

    def _messages_to_contents(self, messages: list[Message]) -> list:
        """Convert our Message list to Gemini contents format."""

        contents = []
        system_instruction = None

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
                continue

            if msg.role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg.content)],
                ))

            elif msg.role == "assistant":
                # Use raw content if available (preserves thought_signature for Gemini 3)
                if hasattr(msg, '_raw_content') and msg._raw_content is not None:
                    # _raw_content is a Gemini Content object stored from prior response
                    raw = cast(types.Content, msg._raw_content)
                    contents.append(raw)
                else:
                    parts = []
                    if msg.content:
                        parts.append(types.Part.from_text(text=msg.content))
                    for tc in msg.tool_calls:
                        parts.append(types.Part.from_function_call(
                            name=tc.name,
                            args=tc.arguments,
                        ))
                    if parts:
                        contents.append(types.Content(role="model", parts=parts))

            elif msg.role == "tool":
                # Tool response — send as function_response
                try:
                    response_data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                except (json.JSONDecodeError, TypeError):
                    response_data = {"result": msg.content}
                # Gemini FunctionResponse requires a dict, not a list
                if not isinstance(response_data, dict):
                    response_data = {"result": response_data}

                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=msg.name,
                        response=response_data,
                    )],
                ))

        # Store system instruction for config
        self._last_system_instruction = system_instruction
        return contents

    def _build_config(self, tools: list[dict] | None, temperature: float, max_tokens: int) -> types.GenerateContentConfig:
        """Build Gemini generation config."""

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        # System instruction
        if hasattr(self, '_last_system_instruction') and self._last_system_instruction:
            config_kwargs["system_instruction"] = self._last_system_instruction

        # Tools
        if tools:
            gemini_tools = self._convert_tools(tools)
            config_kwargs["tools"] = gemini_tools

        return types.GenerateContentConfig(**config_kwargs)

    def _convert_tools(self, tools: list[dict]) -> list:
        """Convert our tool format to Gemini function declarations."""

        declarations = []
        for tool in tools:
            decl = {
                "name": tool["name"],
                "description": tool.get("description", ""),
            }
            if "parameters" in tool:
                decl["parameters"] = tool["parameters"]
            declarations.append(decl)

        return [types.Tool(function_declarations=declarations)]  # type: ignore[arg-type]  # Gemini accepts dicts

    def _parse_response(self, result: Any) -> LLMResponse:
        """Parse Gemini response into our LLMResponse format."""
        content = ""
        tool_calls = []

        if result.candidates:
            candidate = result.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    content += part.text
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    tool_calls.append(ToolCall(
                        id=fc.id or f"call_{fc.name}",
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    ))

        usage = {}
        if hasattr(result, 'usage_metadata') and result.usage_metadata:
            um = result.usage_metadata
            usage = {
                "prompt_tokens": getattr(um, 'prompt_token_count', 0),
                "completion_tokens": getattr(um, 'candidates_token_count', 0),
                "total_tokens": getattr(um, 'total_token_count', 0),
            }

        # Preserve raw content for thought_signature support (Gemini 3)
        raw_content = None
        if result.candidates:
            raw_content = result.candidates[0].content

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=self._model,
            _raw_content=raw_content,
        )

    def _call_with_retry(self, fn: Callable[..., _T], retries: int | None = None) -> _T:
        """Call fn with exponential backoff on transient errors."""
        max_retries = retries if retries is not None else self._max_retries
        last_error = None

        for attempt in range(max_retries):
            try:
                return fn()
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if "429" in error_str or "500" in error_str or "503" in error_str or "resource_exhausted" in error_str:
                    wait = 2 ** attempt
                    logger.warning(
                        "Gemini API error (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, max_retries, wait, e,
                    )
                    time.sleep(wait)
                else:
                    raise

        raise last_error  # type: ignore[misc]


# ── GeminiEmbeddings ─────────────────────────────────────────────────────


class GeminiEmbeddings(EmbeddingProvider):
    """
    Google Gemini embedding provider via the google-genai SDK.

    Uses task types for optimal retrieval:
      - RETRIEVAL_DOCUMENT for indexing documents (embed)
      - RETRIEVAL_QUERY for search queries (embed_query)

    Args:
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        model: Embedding model name (default: gemini-embedding-001).
        dimension: Output embedding dimension (default: 768).
            gemini-embedding-001 natively outputs 3072; truncated to this value.
        max_retries: Number of retry attempts on transient errors (default: 3).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-embedding-001",
        dimension: int = 768,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Gemini API key required. Pass api_key= or set GEMINI_API_KEY env var."
            )
        self._model = model
        self._dimension = dimension
        self._max_retries = max_retries
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """Lazy-init the genai client."""
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed texts for document indexing using RETRIEVAL_DOCUMENT task type.

        Supports batch embedding — multiple texts in one API call.
        """
        if not texts:
            return []

        client = self._get_client()
        result = self._call_with_retry(
            lambda: client.models.embed_content(
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=self._dimension,
                ),
            )
        )

        if result.embeddings is None:
            return []
        vectors = [list(e.values or []) for e in result.embeddings]
        logger.debug("Embedded %d texts → %d-dim vectors", len(texts), self._dimension)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """
        Embed a search query using RETRIEVAL_QUERY task type.

        Uses a different task type than embed() for better retrieval quality.
        """

        client = self._get_client()
        result = self._call_with_retry(
            lambda: client.models.embed_content(
                model=self._model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=self._dimension,
                ),
            )
        )

        if result.embeddings is None:
            return []
        vector = list(result.embeddings[0].values or [])
        logger.debug("Embedded query → %d-dim vector", self._dimension)
        return vector

    def _call_with_retry(self, fn: Callable[..., _T], retries: int | None = None) -> _T:
        """Call fn with exponential backoff retry on transient errors."""
        max_retries = retries if retries is not None else self._max_retries
        last_error = None

        for attempt in range(max_retries):
            try:
                return fn()
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                # Retry on rate limits and transient server errors
                if "429" in error_str or "500" in error_str or "503" in error_str or "resource_exhausted" in error_str:
                    wait = 2 ** attempt
                    logger.warning(
                        "Gemini API error (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, max_retries, wait, e,
                    )
                    time.sleep(wait)
                else:
                    # Non-transient error — don't retry
                    raise

        assert last_error is not None
        raise last_error
