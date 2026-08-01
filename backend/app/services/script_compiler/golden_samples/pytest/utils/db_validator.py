"""
Thin DB validation helper used by dbValidations steps in the Automation
Generation Contract (Pytest renderer). Connection details come from the
environment profile's configured DB validation endpoint (a read-only
service, never a direct DB credential in the script).
"""
import httpx


def _query_row(validation_endpoint: str, query: dict) -> dict:
    response = httpx.post(validation_endpoint, json=query, timeout=30)
    if response.status_code != 200:
        # A transport/endpoint failure is not evidence about the row. Collapsing
        # it into "absent" would let a broken validator satisfy every
        # expect_found=False assertion.
        raise AssertionError(
            f"DB validation endpoint failed ({response.status_code}) for query: {query}"
        )
    return response.json()


def assert_row_exists(validation_endpoint: str, query: dict) -> None:
    body = _query_row(validation_endpoint, query)
    if not body.get("found"):
        raise AssertionError(f"Expected DB row not found for query: {query}")


def assert_row_absent(validation_endpoint: str, query: dict) -> None:
    """The expect_found=False half of the contract.

    Previously this case rendered as assert_row_exists with a TODO comment,
    asserting the exact opposite of what the contract declared.
    """
    body = _query_row(validation_endpoint, query)
    if body.get("found"):
        raise AssertionError(f"DB row was expected to be absent but was found for query: {query}")
