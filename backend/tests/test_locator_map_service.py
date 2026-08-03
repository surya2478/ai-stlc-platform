import anyio

from app.models.locator_map import LocatorMapEntry
from app.services import locator_map_service


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return _ScalarsResult([self._value] if self._value is not None else [])


class _FakeDB:
    def __init__(self, existing: LocatorMapEntry | None = None):
        self.existing = existing
        self.added = []

    async def execute(self, _stmt):
        return _ExecuteResult(self.existing)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        self.added.append(obj)

    async def flush(self):
        return None


def test_upsert_creates_new_entry_when_none_exists():
    db = _FakeDB(existing=None)

    async def run():
        return await locator_map_service.upsert_locator(
            db, project_id=1, application_id=7, page="http://app/login",
            element_name="textbox_username", recommended_locator="page.getByRole('textbox', { name: 'Username' })",
            recommended_strategy="role", confidence_score=90,
        )

    entry = anyio.run(run)
    assert entry in db.added
    assert entry.project_id == 1
    assert entry.confidence_score == 90
    assert entry.last_validated_at is not None


def test_upsert_updates_existing_entry_in_place():
    existing = LocatorMapEntry(
        id=5, project_id=1, application_id=7, page="http://app/login",
        element_name="textbox_username", recommended_locator="page.locator('#u')",
        recommended_strategy="css", confidence_score=40,
    )
    db = _FakeDB(existing=existing)

    async def run():
        return await locator_map_service.upsert_locator(
            db, project_id=1, application_id=7, page="http://app/login",
            element_name="textbox_username",
            recommended_locator="page.getByRole('textbox', { name: 'Username' })",
            recommended_strategy="role", confidence_score=90,
        )

    entry = anyio.run(run)
    assert entry.id == 5  # same row, not a new one
    assert entry.recommended_strategy == "role"
    assert entry.confidence_score == 90
    assert entry not in db.added  # no new row created


def test_record_script_usage_appends_without_duplicating():
    entry = LocatorMapEntry(
        id=1, project_id=1, page="p", element_name="e",
        recommended_locator="x", recommended_strategy="role", used_by_scripts=[10],
    )
    db = _FakeDB()

    async def run():
        await locator_map_service.record_script_usage(db, entry, 10)
        await locator_map_service.record_script_usage(db, entry, 20)

    anyio.run(run)
    assert entry.used_by_scripts == [10, 20]


def test_record_failure_increments_counter():
    entry = LocatorMapEntry(
        id=1, project_id=1, page="p", element_name="e",
        recommended_locator="x", recommended_strategy="role", failure_count=2,
    )
    db = _FakeDB()

    async def run():
        await locator_map_service.record_failure(db, entry)

    anyio.run(run)
    assert entry.failure_count == 3


# ── unbounded page content must not overflow a bounded column ─────────────────
# Observed live 2026-08-03 on Playwright AI Studio project 8: a marketing link
# whose accessible name was a full paragraph produced a 217-character
# element_name and an asyncpg StringDataRightTruncationError against
# locator_map.element_name (varchar 200), failing the whole discovery run.

def _long_name(prefix: str = "link_qa_career_accelerator") -> str:
    return prefix + "_" + "x" * 400


def test_an_over_long_element_name_is_bounded_before_insert():
    db = _FakeDB()

    async def run():
        return await locator_map_service.upsert_locator(
            db, project_id=8, application_id=14, page="https://example.com/",
            element_name=_long_name(), recommended_locator="page.getByRole('link')",
            recommended_strategy="role", confidence_score=90,
        )

    entry = anyio.run(run)

    assert len(entry.element_name) == locator_map_service.ELEMENT_NAME_MAX
    assert entry.element_name.startswith("link_qa_career_accelerator")


def test_an_over_long_page_url_is_bounded_before_insert():
    db = _FakeDB()

    async def run():
        return await locator_map_service.upsert_locator(
            db, project_id=8, application_id=14, page="https://example.com/" + "p" * 800,
            element_name="link_home", recommended_locator="page.getByRole('link')",
            recommended_strategy="role",
        )

    entry = anyio.run(run)

    assert len(entry.page) == locator_map_service.PAGE_MAX


def test_two_long_names_sharing_a_prefix_stay_distinct_rows():
    """Plain truncation would collapse these onto one upsert key, so each
    re-discovery would overwrite the other element's locator."""
    first = locator_map_service.bounded_name(_long_name() + "_alpha", locator_map_service.ELEMENT_NAME_MAX)
    second = locator_map_service.bounded_name(_long_name() + "_beta", locator_map_service.ELEMENT_NAME_MAX)

    assert first != second
    assert len(first) == len(second) == locator_map_service.ELEMENT_NAME_MAX


def test_bounding_is_stable_so_rediscovery_finds_the_same_row():
    """The upsert key has to be deterministic: the same element discovered
    twice must resolve to the row it created, not add a second one."""
    name = _long_name()
    once = locator_map_service.bounded_name(name, locator_map_service.ELEMENT_NAME_MAX)
    twice = locator_map_service.bounded_name(once, locator_map_service.ELEMENT_NAME_MAX)

    assert once == twice
