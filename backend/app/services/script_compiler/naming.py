"""Deterministic naming helpers shared by every renderer — the same contract
always produces the same file names and identifiers."""
from __future__ import annotations

import hashlib
import re


def slugify(*parts: str) -> str:
    text = "_".join(p for p in parts if p).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "unnamed"


def bounded_name(value: str, limit: int) -> str:
    """`value` capped at `limit`, staying unique and stable.

    An element's name comes from its accessible name, which is page content
    and therefore unbounded: a marketing link whose text is a full paragraph
    produced a 217-character identifier and a
    StringDataRightTruncationError on locator_map.element_name (varchar 200).

    Plain truncation would be wrong here, because these names are upsert keys
    — two long names sharing a prefix would collapse onto one row and each
    re-discovery would overwrite the other. Appending a digest of the FULL
    value keeps distinct elements distinct while staying deterministic, so
    re-discovering the same element still lands on the same row.

    Idempotent for anything already within the limit, which is what lets the
    same helper run at both the point a name is generated and the point it is
    persisted without the two disagreeing.
    """
    if len(value) <= limit:
        return value
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=4).hexdigest()
    return f"{value[: limit - len(digest) - 1]}_{digest}"


def env_var_name(binding_name: str) -> str:
    # Split camelCase boundaries first so "productSku" -> "product_Sku" -> "PRODUCT_SKU".
    with_boundaries = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", binding_name)
    return "TEST_" + re.sub(r"[^A-Za-z0-9]+", "_", with_boundaries).strip("_").upper()


def js_string_literal(value: str) -> str:
    """Single-quoted JS/TS string literal with minimal, safe escaping."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def py_string_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
