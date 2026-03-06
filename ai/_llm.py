"""
LLM Client — Provider-agnostic LLM interface with tool/function calling.

Usage::

    from ai import GeminiLLM, Message

    llm = GeminiLLM(api_key="...", model="gemini-3-flash-preview")

    # Simple generation
    response = llm.generate([Message(role="user", content="Hello!")])
    print(response.content)

    # With tools
    tools = [{"name": "search", "description": "Search docs", "parameters": {...}}]
    response = llm.generate([Message(role="user", content="Find reports")], tools=tools)
    if response.tool_calls:
        # Execute tool, send result back
        ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator

from ai._types import LLMResponse, Message

# ── Abstract base class ──────────────────────────────────────────────────


class LLMClient(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Generate a response from the model.

        Args:
            messages: Conversation history as list of Message objects.
            tools: Optional list of tool declarations (OpenAI-style format).
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
            max_tokens: Maximum tokens to generate.

        Returns:
            LLMResponse with content and/or tool_calls.
        """
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """
        Stream response chunks from the model.

        Args:
            Same as generate().

        Yields:
            Partial content strings as they arrive.
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier."""
        ...

    def run_tool_loop(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        execute_tool: Callable | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_iterations: int = 5,
    ) -> LLMResponse:
        """
        Run a generate → tool call → execute → respond loop until the model
        returns a text response (no more tool calls) or max_iterations is reached.

        This handles all the plumbing for tool-calling conversations, including
        preserving provider-specific metadata (thought signatures, etc).

        Args:
            messages: Initial conversation history.
            tools: Tool declarations.
            execute_tool: Callable(name, arguments) → str. Called for each tool call.
                If None, tool calls are returned without execution.
            temperature: Sampling temperature.
            max_tokens: Max tokens per generation.
            max_iterations: Safety limit on tool-call rounds (default: 5).

        Returns:
            Final LLMResponse (the one with text content, or last response if
            max_iterations reached).
        """
        if execute_tool is None:
            return self.generate(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)

        msgs = list(messages)  # Don't mutate caller's list

        for _ in range(max_iterations):
            response = self.generate(msgs, tools=tools, temperature=temperature, max_tokens=max_tokens)

            if not response.tool_calls:
                return response

            # Append assistant message (preserves thought signatures)
            msgs.append(response.to_message())

            # Execute each tool call and append results
            for tc in response.tool_calls:
                result = execute_tool(tc.name, tc.arguments)
                msgs.append(Message(
                    role="tool",
                    content=result,
                    name=tc.name,
                    tool_call_id=tc.id,
                ))

        return response
