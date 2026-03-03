"""
Structured Extraction — Use LLM to extract structured data from unstructured text.

Given a text and a JSON schema, the LLM extracts matching fields and returns
validated structured data.

Usage::

    from ai import GeminiLLM, extract

    llm = GeminiLLM(api_key="...")
    result = extract(
        llm,
        text="John Smith, age 35, works at Acme Corp as a senior engineer.",
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "company": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["name"],
        },
    )
    print(result.data)  # {"name": "John Smith", "age": 35, ...}
"""

from __future__ import annotations

import json
import logging

from ai._llm import LLMClient
from ai._types import ExtractionResult, Message

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """Extract structured data from the following text according to the JSON schema below.

## JSON Schema
```json
{schema}
```

## Text
{text}

## Instructions
- Return ONLY a valid JSON object matching the schema above.
- Do not include any explanation, markdown formatting, or code fences.
- If a field cannot be determined from the text, use null.
- For array fields, return an empty array if no items found."""


def extract(
    llm: LLMClient,
    text: str,
    schema: dict,
    model_class: type | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.0,
) -> ExtractionResult:
    """
    Extract structured data from text using an LLM.

    Args:
        llm: An LLMClient instance.
        text: The unstructured text to extract from.
        schema: JSON Schema describing the expected output structure.
        model_class: Optional dataclass/class to instantiate with extracted data.
            If provided, result.data will be an instance of this class.
        system_prompt: Optional custom system prompt.
        temperature: LLM temperature (default: 0.0 for deterministic extraction).

    Returns:
        ExtractionResult with extracted data (dict or model_class instance).
    """
    sys_prompt = system_prompt or "You are a precise data extraction assistant. Extract structured data exactly as requested."

    user_content = EXTRACTION_PROMPT.format(
        schema=json.dumps(schema, indent=2),
        text=text,
    )

    messages = [
        Message(role="system", content=sys_prompt),
        Message(role="user", content=user_content),
    ]

    response = llm.generate(messages, temperature=temperature)
    raw = response.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse extraction JSON: %s\nRaw: %s", e, raw[:500])
        # Try to find JSON object in the response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end])
            except json.JSONDecodeError:
                raise ValueError(f"LLM returned invalid JSON: {raw[:200]}") from e
        else:
            raise ValueError(f"LLM returned invalid JSON: {raw[:200]}") from e

    # Optionally instantiate model class
    if model_class is not None:
        try:
            data = model_class(**data)
        except Exception as e:
            logger.warning("Failed to instantiate %s: %s", model_class.__name__, e)
            # Return raw dict if instantiation fails

    logger.info("Extracted %d fields from text (%d chars)",
                len(data) if isinstance(data, dict) else 1, len(text))

    return ExtractionResult(
        data=data,
        raw_response=response.content,
        usage=response.usage,
    )
