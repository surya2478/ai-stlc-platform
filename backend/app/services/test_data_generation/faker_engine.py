"""Faker-based test data generator.

Schema shape (input):

  {
    "locale": "en_US",
    "fields": [
      { "name": "customer_id", "provider": "uuid4" },
      { "name": "first_name",  "provider": "first_name" },
      { "name": "email",       "provider": "email" },
      { "name": "msisdn",      "provider": "msisdn", "params": { "country": "IN" } },
      { "name": "balance",     "provider": "pydecimal",
        "params": { "left_digits": 4, "right_digits": 2, "positive": true } }
    ]
  }

Each field references a provider method on the Faker instance — built-in
(`first_name`, `email`, `uuid4`, …) or one from telco_providers (`msisdn`,
`imsi`, …). `params` is forwarded as keyword arguments.

Validation:
  - Locale falls back to `en_US` with a warning if unavailable.
  - Unknown provider names raise FakerEngineError before any rows are generated,
    so the caller can return a 422 with a useful message instead of crashing
    mid-batch.
  - decimal / date / datetime outputs are coerced to JSON-safe primitives.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from faker import Faker
from faker.exceptions import UniquenessException

from app.services.test_data_generation.telco_providers import register_telco_providers

logger = logging.getLogger(__name__)

# Locales we've smoke-tested. Others may work but we whitelist these in the
# warning logic so we don't spam logs for every variant the user picks.
_KNOWN_LOCALES = frozenset({
    "en_US", "en_GB", "en_IN", "en_AU", "en_CA",
    "de_DE", "fr_FR", "es_ES", "it_IT", "pt_BR",
    "ja_JP", "zh_CN", "ar_SA",
})


class FakerEngineError(Exception):
    """Raised on schema / provider problems before any rows are generated."""


# Hard cap on schema size so a runaway schema can't degrade the worker.
# 100 fields is well above anything a real test data row needs.
_MAX_FIELDS_PER_SCHEMA = 100


@dataclass(slots=True)
class GeneratedField:
    name: str
    provider: str
    params: dict[str, Any]


def _normalise_fields(schema: dict[str, Any]) -> list[GeneratedField]:
    fields = schema.get("fields")
    if not isinstance(fields, list) or not fields:
        raise FakerEngineError(
            "schema.fields must be a non-empty list of {name, provider, params?} objects."
        )
    if len(fields) > _MAX_FIELDS_PER_SCHEMA:
        raise FakerEngineError(
            f"schema.fields contains {len(fields)} entries; max {_MAX_FIELDS_PER_SCHEMA} per request."
        )

    out: list[GeneratedField] = []
    seen: set[str] = set()
    for idx, raw in enumerate(fields):
        if not isinstance(raw, dict):
            raise FakerEngineError(f"fields[{idx}] must be an object, got {type(raw).__name__}.")
        name = str(raw.get("name") or "").strip()
        provider = str(raw.get("provider") or "").strip()
        if not name:
            raise FakerEngineError(f"fields[{idx}].name is required.")
        if not provider:
            raise FakerEngineError(f"fields[{idx}].provider is required (field '{name}').")
        if name in seen:
            raise FakerEngineError(f"fields[{idx}].name '{name}' is duplicated.")
        seen.add(name)
        params = raw.get("params") or {}
        if not isinstance(params, dict):
            raise FakerEngineError(f"fields[{idx}].params for '{name}' must be an object.")
        out.append(GeneratedField(name=name, provider=provider, params=dict(params)))
    return out


def _build_faker(locale: Any) -> tuple[Faker, str]:
    # Coerce non-string locales (None, ints, …) to en_US instead of crashing
    # in str.strip().
    if not isinstance(locale, str) or not locale.strip():
        requested = "en_US"
    else:
        requested = locale.strip()
    try:
        fake = Faker(requested)
    except AttributeError:
        # Faker raises AttributeError for unknown locales when accessing them later;
        # construction itself usually accepts anything. Belt and braces.
        if requested in _KNOWN_LOCALES:
            raise
        logger.warning("Faker locale '%s' unavailable; falling back to en_US.", requested)
        fake = Faker("en_US")
        requested = "en_US"
    register_telco_providers(fake)
    return fake, requested


def _validate_providers(fake: Faker, fields: list[GeneratedField]) -> None:
    missing = [f for f in fields if not callable(getattr(fake, f.provider, None))]
    if missing:
        names = ", ".join(f"'{f.provider}' (field '{f.name}')" for f in missing)
        raise FakerEngineError(
            f"Unknown Faker provider(s): {names}. "
            "Use a built-in provider (e.g. first_name, email, uuid4, address) "
            "or a telco provider (msisdn, imsi, imei, iccid, lac, cell_id, tac)."
        )


def _jsonify(value: Any) -> Any:
    if isinstance(value, Decimal):
        # Preserve numeric form; JSON has no Decimal so float is the best we get.
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


def generate_records(schema: dict[str, Any], count: int, *, seed: int | None = None) -> list[dict[str, Any]]:
    """Produce `count` records following `schema`.

    Raises FakerEngineError on schema / provider problems. Per-row provider
    failures (e.g. UniquenessException after many attempts) are caught and
    surfaced as a Faker engine error with context.
    """
    if count <= 0:
        return []
    if count > 10000:
        raise FakerEngineError("count must be ≤ 10000 per request.")

    fields = _normalise_fields(schema)
    fake, _resolved_locale = _build_faker(schema.get("locale"))
    _validate_providers(fake, fields)

    if seed is not None:
        # Use instance-level seeding so concurrent requests don't pollute each
        # other's random state via the class-level Faker.seed(...) generator.
        fake.seed_instance(seed)

    rows: list[dict[str, Any]] = []
    for row_idx in range(count):
        record: dict[str, Any] = {}
        for field in fields:
            try:
                value = getattr(fake, field.provider)(**field.params)
            except UniquenessException as exc:
                raise FakerEngineError(
                    f"Faker could not produce a unique '{field.provider}' value "
                    f"for field '{field.name}' at row {row_idx + 1}: {exc}."
                )
            except TypeError as exc:
                raise FakerEngineError(
                    f"Provider '{field.provider}' rejected the params for "
                    f"field '{field.name}': {exc}."
                )
            record[field.name] = _jsonify(value)
        rows.append(record)
    return rows
