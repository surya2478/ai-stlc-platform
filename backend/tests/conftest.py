"""Test session configuration.

Forces the unpooled database strategy for the whole test run, before any test
module imports the application.

`app.database` builds its engine at import time and picks QueuePool or
NullPool from DB_POOL_ENABLED, whose default is True. A pooled async engine
keeps asyncpg connections bound to the event loop that opened them, and each
`TestClient(app)` runs the ASGI app in a loop of its own that it closes on
exit. So the first test that actually reaches the database leaves a
connection in the pool, and the next one to check that connection out gets one
whose loop is gone: the request dies with "Event loop is closed" and the
endpoint returns 500.

That surfaced as test_xss_attempt_in_json_body failing only when the whole
file ran — it registers a valid user, so it is one of the few input-validation
tests that gets past validation to a query, and the test before it that also
reaches the database is test_oversized_json_body_rejected. On its own it
passed, which is what made it look like an endpoint bug rather than shared
state between two clients.

NullPool opens a connection per checkout and closes it at the end, so nothing
outlives the loop that created it. database.py already documents this as the
testing configuration; nothing was setting it.

This must be a plain assignment rather than setdefault: the value being
overridden is the one the surrounding deployment exports.
"""
import os

os.environ["DB_POOL_ENABLED"] = "false"

# Only matters if something imported app.config before this module — pytest
# plugins can — in which case the cached Settings still carries the old value.
try:  # pragma: no cover - import-order guard
    from app.config import get_settings

    get_settings.cache_clear()
except Exception:  # pragma: no cover - app not importable yet is the normal case
    pass
