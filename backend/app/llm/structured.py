"""Pydantic validation helpers for structured LLM output."""
from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

T = TypeVar("T", bound=BaseModel)


def validate_structured_output(data: Any, schema: type[T]) -> T:
    """Validate a single LLM object against a Pydantic schema."""
    return TypeAdapter(schema).validate_python(data)


def validate_structured_list(data: Any, schema: type[T]) -> list[dict[str, Any]]:
    """Validate a list of LLM objects and return JSON-safe dictionaries."""
    validated = TypeAdapter(list[schema]).validate_python(data)  # type: ignore[valid-type]
    return [item.model_dump(mode="json") for item in validated]


def clean_json_text(text: str) -> str:
    """Strip markdown code block tags if present and locate JSON arrays/objects."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Fallback to finding the first '[' or '{' and last ']' or '}' if surrounded by clutter
    if not (text.startswith("[") or text.startswith("{")):
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        if match:
            text = match.group(0)
    return text


def check_content_safety(val: Any) -> None:
    """Recursively validate that no strings contain executable HTML/JS script injection."""
    if isinstance(val, str):
        lower_val = val.lower()
        if "<script" in lower_val:
            raise ValueError("Safety validation failed: executable script tag detected in output.")
        if "javascript:" in lower_val:
            raise ValueError("Safety validation failed: javascript: protocol detected in output.")
        if re.search(r"\bon(?:error|load|click|dbclick|mouseover|mouseout|mouseenter|mouseleave|focus|blur|change|submit|keydown|keypress|keyup|select|reset)\s*=", lower_val):
            raise ValueError("Safety validation failed: inline script handler detected in output.")
    elif isinstance(val, dict):
        for k, v in val.items():
            check_content_safety(v)
    elif isinstance(val, list):
        for item in val:
            check_content_safety(item)


def parse_and_validate_llm_output(text: str, schema: type[T]) -> T:
    """Parse JSON string and validate against Pydantic schema."""
    if text and len(text) > 500000:
        raise ValueError("LLM output length exceeds safety limit of 500,000 characters.")
    cleaned = clean_json_text(text)
    try:
        raw = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM output is not valid JSON: {exc}")
    
    # Content safety check on raw values
    check_content_safety(raw)

    try:
        return validate_structured_output(raw, schema)
    except ValidationError as exc:
        raise ValueError(f"LLM output failed Pydantic schema validation: {exc}")


def parse_and_validate_llm_list(text: str, schema: type[T]) -> list[dict[str, Any]]:
    """Parse JSON array string and validate its items against Pydantic schema."""
    if text and len(text) > 500000:
        raise ValueError("LLM output length exceeds safety limit of 500,000 characters.")
    cleaned = clean_json_text(text)
    try:
        raw = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM output is not valid JSON: {exc}")
    
    # Content safety check on raw values
    check_content_safety(raw)

    try:
        return validate_structured_list(raw, schema)
    except ValidationError as exc:
        raise ValueError(f"LLM output failed Pydantic list validation: {exc}")
