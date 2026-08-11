"""LLM provider boundary for Instructor-backed OpenRouter structured output.

Callers supply a Pydantic response model and receive a validated instance. This
package owns provider selection and configuration availability; it provides no
free-text completion API.
"""

from __future__ import annotations

from app.llm.availability import describe_availability, require_llm
from app.llm.client import StructuredLLMClient, get_structured_client

__all__ = [
    "StructuredLLMClient",
    "describe_availability",
    "get_structured_client",
    "require_llm",
]
