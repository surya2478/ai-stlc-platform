"""
Thin DB validation helper used by dbValidations steps in the Automation
Generation Contract (Pytest renderer). Connection details come from the
environment profile's configured DB validation endpoint (a read-only
service, never a direct DB credential in the script).
"""
import httpx


def assert_row_exists(validation_endpoint: str, query: dict) -> None:
    response = httpx.post(validation_endpoint, json=query, timeout=30)
    if response.status_code != 200:
        raise AssertionError(f"DB validation request failed for query: {query}")
    body = response.json()
    if not body.get("found"):
        raise AssertionError(f"Expected DB row not found for query: {query}")
