"""
Public data types for the ai package.

These are the only types users interact with directly.
All are re-exported from ai/__init__.py.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Message:
    """A message in a conversation."""
    role: str               # "user", "assistant", "system", "tool"
    content: str = ""       # Text content
    tool_calls: list = field(default_factory=list)  # ToolCalls from assistant
    tool_call_id: str = ""  # For tool response messages
    name: str = ""          # Tool name for tool responses
    _raw_content: object = field(default=None, repr=False)  # Provider-specific raw content


@dataclass
class ToolCall:
    """A tool/function call requested by the model."""
    id: str             # Call ID
    name: str           # Function name
    arguments: dict     # Parsed arguments


@dataclass
class LLMResponse:
    """Response from an LLM generation call."""
    content: str = ""                           # Generated text
    tool_calls: list[ToolCall] = field(default_factory=list)  # Tool calls
    usage: dict = field(default_factory=dict)   # Token usage stats
    model: str = ""                             # Model used
    _raw_content: object = field(default=None, repr=False)  # Provider-specific raw content

    def to_message(self) -> Message:
        """
        Convert this response to a Message for conversation history.

        Preserves provider-specific metadata (e.g. Gemini thought signatures)
        so tool-calling loops work correctly without manual wiring.
        """
        msg = Message(
            role="assistant",
            content=self.content,
            tool_calls=list(self.tool_calls),
        )
        msg._raw_content = self._raw_content
        return msg


@dataclass
class RAGResult:
    """Result from a RAG pipeline query."""
    answer: str                                     # LLM's answer
    sources: list[dict] = field(default_factory=list)  # Retrieved chunks used as context
    usage: dict = field(default_factory=dict)        # Token usage


@dataclass
class ExtractionResult:
    """Result from structured extraction."""
    data: dict                                       # Extracted structured data
    raw_response: str = ""                           # Raw LLM response
    usage: dict = field(default_factory=dict)        # Token usage


@dataclass
class Tool:
    """A callable tool with JSON schema declaration."""
    name: str
    description: str
    parameters: dict            # JSON Schema for arguments
    fn: Callable[..., str]      # Execute function → returns JSON string


@runtime_checkable
class DocumentStore(Protocol):
    """Protocol for document storage backends used by RAG and search tools.

    MediaStore satisfies this interface. Any object implementing these
    methods can be used with AI.ask() and AI.search_tools().
    """

    def search(self, query: str, *, content_type: str | None = None, limit: int = 10) -> list[dict]:
        """Full-text keyword search over documents."""
        ...

    def semantic_search(self, query: str, *, limit: int = 10) -> list[dict]:
        """Semantic similarity search over document chunks."""
        ...

    def hybrid_search(self, query: str, *, limit: int = 10) -> list[dict]:
        """Combined keyword + semantic search."""
        ...

    def list(self, *, content_type: str | None = None, limit: int = 20) -> list:
        """List documents, optionally filtered by content type."""
        ...
