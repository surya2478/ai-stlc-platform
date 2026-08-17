"""Application discovery for the studio — credentials, crawl, element catalog.

Screen 1 gains one capability here: point the studio at the running
application and record what is actually on the page. Everything downstream
(grounding on Screen 2, compiled scripts on Screen 3) reads the catalog this
produces; without a discovery run they behave exactly as they did before,
ungrounded.

Credentials are the one genuinely sensitive thing this module stores. They
are Fernet-encrypted with an HKDF key derived from the app secret — the same
construction `jira_service` and `mcp_connection_service` already use, with
its own salt and info string so a leak of one domain's key material cannot
decrypt another's. `decrypt_credentials` is called in exactly one place (the
discovery worker, immediately before typing them into the browser) and the
plaintext is never returned by a route, written to a log, or included in an
agent's `input_data`.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.test_automation_studio.discovery_agent import (
    DEFAULT_MAX_PAGES,
    TasDiscoveryAgent,
)
from app.config import get_settings
from app.models.test_automation_studio import (
    TasDiscoveredElement,
    TasDiscoveryRun,
    TasIntakeBatch,
    TasSourceTestCase,
)
from app.services import agent_run_service
from app.services.test_automation_studio.progress import ProgressCallback
from app.services.test_automation_studio.progress import report as _report

logger = logging.getLogger(__name__)
settings = get_settings()

_HKDF_SALT = b"stlc-platform-tas-discovery-v1"
_HKDF_INFO = b"tas-batch-application-credentials"

# How much test case text is fed to the crawler as relevance signal. The
# crawler only uses it to rank which links are worth spending a page budget
# on, so a bounded sample is as good as the whole corpus and keeps the
# agent's input small.
_RELEVANCE_SAMPLE = 40


def _fernet() -> Fernet:
    hkdf = HKDF(algorithm=SHA256(), length=32, salt=_HKDF_SALT, info=_HKDF_INFO)
    return Fernet(base64.urlsafe_b64encode(hkdf.derive(settings.app_secret_key.encode("utf-8"))))


def encrypt_credentials(credentials: dict[str, str] | None) -> str | None:
    if not credentials or not credentials.get("username") or not credentials.get("password"):
        return None
    payload = {"username": credentials["username"], "password": credentials["password"]}
    return _fernet().encrypt(json.dumps(payload).encode("utf-8")).decode("utf-8")


def decrypt_credentials(value: str | None) -> dict[str, str]:
    """The only reader of the stored secret. Returns {} on any failure —
    a rotated app secret must degrade to "sign-in skipped, no credentials",
    never to a crash inside the worker."""
    if not value:
        return {}
    try:
        data = json.loads(_fernet().decrypt(value.encode("utf-8")).decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError):
        logger.warning("Stored studio credentials could not be decrypted")
        return {}
    return data if isinstance(data, dict) else {}


# ── Batch credential configuration ───────────────────────────────────────────

def apply_auth_settings(
    batch: TasIntakeBatch,
    updates: dict,
    *,
    user_id: int,
    previous_login_url: str | None = None,
    previous_application_url: str | None = None,
) -> None:
    """Apply the batch form's credentials block.

    `auth_mode="none"` clears the stored secret rather than orphaning it —
    turning sign-in off must actually remove the password, not just stop
    using it. A `form` update that omits the password keeps whatever was
    already stored, so re-saving the form to change a field label does not
    silently wipe the credentials.

    That retention is scoped to the destination the credentials were entered
    for. The secret is write-only — no route returns it, and `has_credentials`
    is all a reader ever sees — so if the sign-in target could be moved while
    the secret stayed put, anyone who could edit the batch could have the
    worker type someone else's password into a page of their choosing. Moving
    `login_url` or `application_url` therefore drops the stored secret: the
    credentials must be re-entered by someone who already knows them. The
    caller passes the pre-edit values because `apply_batch_fields` has already
    written the new `application_url` onto the batch by the time we run.
    """
    if "auth_mode" in updates and updates["auth_mode"] is not None:
        batch.auth_mode = updates["auth_mode"]
    if "auth_config" in updates and updates["auth_config"] is not None:
        batch.auth_config = {
            key: value
            for key, value in updates["auth_config"].items()
            if key in ("login_url", "username_label", "password_label", "submit_label")
            and value is not None
        }

    if batch.auth_mode == "none":
        batch.auth_secret_encrypted = None
        return

    login_url = (batch.auth_config or {}).get("login_url")
    if (login_url, batch.application_url) != (previous_login_url, previous_application_url):
        batch.auth_secret_encrypted = None

    username = updates.get("auth_username")
    password = updates.get("auth_password")
    if username and password:
        batch.auth_secret_encrypted = encrypt_credentials(
            {"username": username, "password": password}
        )
    batch.updated_by = user_id


# ── Discovery runs ───────────────────────────────────────────────────────────

async def latest_run(db: AsyncSession, batch_id: int) -> TasDiscoveryRun | None:
    return (
        await db.execute(
            select(TasDiscoveryRun)
            .where(TasDiscoveryRun.batch_id == batch_id)
            .order_by(TasDiscoveryRun.version.desc())
            .limit(1)
        )
    ).scalars().first()


async def get_run_or_404(db: AsyncSession, run_id: int) -> TasDiscoveryRun:
    run = await db.get(TasDiscoveryRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovery run not found")
    return run


async def list_elements(
    db: AsyncSession, *, discovery_run_id: int, page_url: str | None = None
) -> list[TasDiscoveredElement]:
    query = select(TasDiscoveredElement).where(
        TasDiscoveredElement.discovery_run_id == discovery_run_id
    )
    if page_url:
        query = query.where(TasDiscoveredElement.page_url == page_url)
    query = query.order_by(
        TasDiscoveredElement.page_url.asc(),
        TasDiscoveredElement.confidence_score.desc(),
        TasDiscoveredElement.element_name.asc(),
    )
    return list((await db.execute(query)).scalars().all())


async def current_catalog(db: AsyncSession, batch_id: int) -> tuple[TasDiscoveryRun | None, list[dict]]:
    """The catalog grounding and generation consume, in `locator_map` shape.

    Deliberately the same dict keys the classic automation stack uses
    (`element_name`, `recommended_locator`, `confidence_score`, `page`) so
    `locator_policy.select_relevant_catalog`, `filter_catalog_by_page` and
    `ground_page_object_elements` work against it unmodified. Reimplementing
    those against a studio-specific shape would mean maintaining two copies
    of logic that already took several live failures to get right.
    """
    run = (
        await db.execute(
            select(TasDiscoveryRun)
            .where(
                TasDiscoveryRun.batch_id == batch_id,
                TasDiscoveryRun.is_current.is_(True),
                TasDiscoveryRun.status == "completed",
            )
            .order_by(TasDiscoveryRun.version.desc())
            .limit(1)
        )
    ).scalars().first()
    if run is None:
        return None, []
    rows = await list_elements(db, discovery_run_id=run.id)
    return run, [
        {
            "element_name": row.element_name,
            "page": row.page_url,
            "role": row.role,
            "accessible_name": row.accessible_name,
            "business_meaning": row.business_meaning,
            "recommended_locator": row.recommended_locator,
            "recommended_strategy": row.recommended_strategy,
            "confidence_score": row.confidence_score,
        }
        for row in rows
    ]


async def _relevance_text(db: AsyncSession, batch_id: int) -> str:
    """Test case titles from this batch, used only to rank which links the
    bounded crawl should spend its page budget on."""
    titles = (
        await db.execute(
            select(TasSourceTestCase.title)
            .where(TasSourceTestCase.batch_id == batch_id)
            .limit(_RELEVANCE_SAMPLE)
        )
    ).scalars().all()
    return " ".join(t for t in titles if t)


async def prepare_discovery(db: AsyncSession, *, batch: TasIntakeBatch) -> None:
    """Refuse a run that cannot possibly work, before it is queued."""
    if not (batch.application_url or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This batch has no application URL. Set one on the batch before running "
                "discovery — there is nothing to open without it."
            ),
        )
    if batch.auth_mode == "form" and not batch.auth_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Sign-in is set to 'form' but no credentials are stored for this batch. "
                "Enter a username and password, or set sign-in to 'none'."
            ),
        )


async def execute_discovery(
    db: AsyncSession,
    *,
    batch_id: int,
    user_id: int,
    run=None,
    on_progress: ProgressCallback | None = None,
) -> TasDiscoveryRun:
    """Crawl the batch's application and persist the element catalog.

    A failed crawl is still persisted as a run row. Screen 1 has to be able
    to show *why* discovery failed — wrong credentials, unreachable URL — and
    a failure that leaves no row behind looks identical to never having tried.
    """
    batch = await db.get(TasIntakeBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake batch not found")

    previous = await latest_run(db, batch_id)
    version = (previous.version + 1) if previous is not None else 1
    if previous is not None and previous.is_current:
        previous.is_current = False
        db.add(previous)

    discovery_run = TasDiscoveryRun(
        project_id=batch.project_id,
        batch_id=batch.id,
        version=version,
        is_current=True,
        status="running",
        application_url=batch.application_url,
        application_environment=batch.application_environment,
        auth_mode=batch.auth_mode,
        auth_status="not_required" if batch.auth_mode == "none" else "skipped",
        agent_run_id=getattr(run, "id", None),
        created_by=user_id,
    )
    db.add(discovery_run)
    await db.flush()

    await _report(on_progress, 15, f"Opening {batch.application_url}")

    agent = TasDiscoveryAgent()
    result = await agent.run(
        application_url=batch.application_url or "",
        auth_mode=batch.auth_mode,
        auth_config=batch.auth_config or {},
        credentials=decrypt_credentials(batch.auth_secret_encrypted),
        relevance_text=await _relevance_text(db, batch_id),
        max_pages=DEFAULT_MAX_PAGES,
    )

    if not result.success:
        discovery_run.status = "failed"
        discovery_run.error = (result.error or "Discovery failed")[:4000]
        discovery_run.blockers = (result.data or {}).get("blockers") or []
        db.add(discovery_run)
        if run is not None:
            await agent_run_service.complete_agent_run(
                db, run, output_data={"discovery_run_id": discovery_run.id, "status": "failed"}
            )
        await db.commit()
        await db.refresh(discovery_run)
        return discovery_run

    await _report(on_progress, 75, "Recording discovered elements")

    pages = result.data.get("pages") or []
    seen: set[tuple[str, str]] = set()
    element_rows = 0
    for page in pages:
        page_url = (page.get("url") or "")[:1000]
        page_title = (page.get("title") or None)
        for element in page.get("elements") or []:
            key = (page_url, element["element_name"])
            if key in seen:
                # The unique constraint would reject it anyway; skipping here
                # keeps one duplicate from aborting the whole run's insert.
                continue
            seen.add(key)
            db.add(
                TasDiscoveredElement(
                    project_id=batch.project_id,
                    batch_id=batch.id,
                    discovery_run_id=discovery_run.id,
                    page_url=page_url,
                    page_title=page_title[:500] if page_title else None,
                    element_name=element["element_name"],
                    role=element.get("role"),
                    accessible_name=element.get("accessible_name"),
                    business_meaning=element.get("business_meaning"),
                    recommended_locator=element["recommended_locator"],
                    recommended_strategy=element.get("recommended_strategy") or "role",
                    confidence_score=int(element.get("confidence_score") or 0),
                    href=element.get("href"),
                )
            )
            element_rows += 1

    discovery_run.status = "completed"
    discovery_run.auth_status = result.data.get("auth_status") or discovery_run.auth_status
    discovery_run.auth_detail = result.data.get("auth_detail")
    discovery_run.pages_discovered = len(pages)
    discovery_run.elements_discovered = element_rows
    discovery_run.explored_pages = [
        {
            "url": page.get("url"),
            "title": page.get("title"),
            "element_count": len(page.get("elements") or []),
        }
        for page in pages
    ]
    db.add(discovery_run)

    if run is not None:
        await agent_run_service.complete_agent_run(
            db,
            run,
            output_data={
                "discovery_run_id": discovery_run.id,
                "pages": len(pages),
                "elements": element_rows,
                "auth_status": discovery_run.auth_status,
            },
        )
    await db.commit()
    await db.refresh(discovery_run)
    return discovery_run


async def delete_runs(db: AsyncSession, *, batch_id: int) -> int:
    """Discard every discovery run for a batch, catalog included.

    Refined test cases keep their `grounding_summary` but their
    `discovery_run_id` goes null (SET NULL), which is the honest state: the
    grounding happened, the evidence behind it is gone, and re-grounding is
    the way back.
    """
    rows = list(
        (
            await db.execute(select(TasDiscoveryRun.id).where(TasDiscoveryRun.batch_id == batch_id))
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0
    await db.execute(
        sql_delete(TasDiscoveryRun)
        .where(TasDiscoveryRun.id.in_(rows))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return len(rows)


# ── Serialization ────────────────────────────────────────────────────────────

def serialize_run(run: TasDiscoveryRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "project_id": run.project_id,
        "batch_id": run.batch_id,
        "version": run.version,
        "is_current": run.is_current,
        "status": run.status,
        "application_url": run.application_url,
        "application_environment": run.application_environment,
        "auth_mode": run.auth_mode,
        "auth_status": run.auth_status,
        "auth_detail": run.auth_detail,
        "pages_discovered": run.pages_discovered,
        "elements_discovered": run.elements_discovered,
        "explored_pages": run.explored_pages or [],
        "blockers": run.blockers or [],
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def stale_against(run: TasDiscoveryRun | None, grounded_at: datetime | None) -> bool:
    """True when a newer discovery run exists than the one a test case was
    grounded against — the screen shows this so a stale badge is never
    mistaken for a fresh one."""
    if run is None or grounded_at is None:
        return False
    created = run.created_at
    if created is None:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if grounded_at.tzinfo is None:
        grounded_at = grounded_at.replace(tzinfo=timezone.utc)
    return created > grounded_at
