"""Deterministic naming helpers shared by every renderer — the same contract
always produces the same file names and identifiers."""
from __future__ import annotations

import re


def slugify(*parts: str) -> str:
    text = "_".join(p for p in parts if p).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "unnamed"


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
