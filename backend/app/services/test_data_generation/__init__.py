"""Test data generation package.

Exports the Faker-based engine plus telco-specific providers. The legacy
external_test_data_tools module routes a generate request to LocalFakerToolClient
when the user picks "Faker" as the external tool.
"""
from app.services.test_data_generation.faker_engine import (  # noqa: F401
    FakerEngineError,
    GeneratedField,
    generate_records,
)
from app.services.test_data_generation.telco_providers import register_telco_providers  # noqa: F401
