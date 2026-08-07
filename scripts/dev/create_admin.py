"""Bootstrap the first platform admin.

A fresh database has no way to reach an admin account. `/users/register` is
public but hardcodes `role="qa_engineer"` and `is_superuser=False`, the login
page deliberately exposes no signup form, and `set_password.py` only rewrites
the password of an account that already exists. That left a clean deployment
with no supported route to platform admin at all, short of writing SQL by hand.

This script closes that gap, and only that gap.

Deliberately kept OUTSIDE `backend/`, for the same reason as
`set_password.py`: the backend image is built with `context: ./backend` and a
`COPY . .`, so a file placed there ships to every deployment. Living at the
repo root means it is physically absent from the image rather than merely
excluded by a rule someone could later "tidy up". The repo is bind-mounted at
/repo in the dev containers, so it still runs:

    docker exec -it stlc_backend python /repo/scripts/dev/create_admin.py

Safety properties:
  - Refuses to run while ANY active platform admin exists. That is the whole
    guard, and it is what makes the script safe outside local: bootstrapping
    is not privilege escalation when there is no privilege to escalate from.
    Once an admin exists, promotion belongs to the admin API, which audits.
  - Unlike `set_password.py` this is NOT gated on APP_ENV. A staging or
    production deployment needs a first admin exactly as much as a local one,
    and the "no admin exists" check is a stronger guarantee than an
    environment name.
  - The password is read with getpass, so it is never echoed and never lands
    in shell history. Nothing is written to disk or logged.
  - The new password must satisfy the platform's own strength policy, so this
    tool cannot mint a credential that `/users/register` would have rejected.
  - The email is normalised the same way login normalises it.

This grants no capability that `docker exec` did not already grant — anyone
who can run this can already reach the database directly. It is a convenience,
and it is guarded accordingly.
"""
from __future__ import annotations

import getpass
import sys

import anyio
from sqlalchemy import func, or_, select

from app.core.password_validation import validate_password_strength
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.rbac_service import GLOBAL_ADMIN_ROLES

# bcrypt silently truncates beyond 72 bytes, so a longer password would not be
# the password the user thinks they set.
_MAX_PASSWORD_BYTES = 72


async def _existing_active_admins(db) -> list[User]:
    """Every active account that already holds platform admin.

    Mirrors `rbac_service.is_platform_admin`: the superuser flag OR a role in
    GLOBAL_ADMIN_ROLES. Both halves matter — an account can be admin by role
    without the flag, and the flag alone is enough without the role.
    """
    result = await db.execute(
        select(User).where(
            User.is_active.is_(True),
            # GLOBAL_ADMIN_ROLES is a set; in_() wants an ordered sequence.
            or_(User.is_superuser.is_(True), User.role.in_(sorted(GLOBAL_ADMIN_ROLES))),
        )
    )
    return list(result.scalars().all())


def _prompt_password() -> str:
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match. Nothing was changed.")
        sys.exit(1)
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        print(f"Password must be at most {_MAX_PASSWORD_BYTES} bytes — bcrypt truncates anything longer.")
        sys.exit(1)
    try:
        validate_password_strength(password)
    except ValueError as exc:
        print(f"{exc} Nothing was changed.")
        sys.exit(1)
    return password


async def _bootstrap() -> None:
    """The whole flow, inside a single event loop.

    Everything runs under one `anyio.run` on purpose. `AsyncSessionLocal` is
    backed by a module-level engine whose connection pool binds to the loop
    that first used it, so a second `anyio.run` in the same process fails with
    "got Future attached to a different loop". `set_password.py` gets away
    with prompting first because it only ever enters the loop once; this
    script has to interleave prompts with queries, so the prompts come inside.

    Each query gets its own short-lived session rather than one session held
    open across the prompts — blocking input() while holding a pooled
    connection and an open transaction is how a CLI ties up the database for
    as long as someone leaves the terminal unattended.
    """
    async with AsyncSessionLocal() as db:
        admins = await _existing_active_admins(db)
        if admins:
            print(f"Refusing to run: {len(admins)} active platform admin(s) already exist:")
            for admin in admins:
                print(f"  id {admin.id}: {admin.email!r} (role {admin.role}, superuser {admin.is_superuser})")
            print("Bootstrapping is only for a deployment with no admin at all.")
            print("Grant admin to another account through the admin API, which records an audit entry.")
            sys.exit(1)

    raw_email = input("Email: ").strip()
    # Login lowercases the address before looking it up, so normalise here too.
    email = raw_email.lower()
    if email != raw_email:
        print(f"Normalised to {email}")
    if not email:
        print("Email is required. Nothing was changed.")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        # Case-insensitive lookup, matching set_password.py: `create_user`
        # historically stored the address as typed, so a row may exist with
        # different capitalisation than the one login would search for.
        result = await db.execute(select(User).where(func.lower(User.email) == email))
        existing = list(result.scalars().all())

        if len(existing) > 1:
            print(f"{len(existing)} accounts share this address, differing only in case:")
            for user in existing:
                print(f"  id {user.id}: {user.email!r} (role {user.role}, active {user.is_active})")
            print("Refusing to guess which one you meant — resolve the duplicates first.")
            sys.exit(1)

        if existing:
            # The common path after registering through /users/register: the
            # account is real, it just came out as qa_engineer. Promote it and
            # leave its password alone — set_password.py owns credentials.
            user = existing[0]
            user.role = "admin"
            user.is_superuser = True
            user.is_active = True
            await db.commit()
            print(f"Promoted {user.email} (id {user.id}) to platform admin.")
            print("Password unchanged — use set_password.py if you need to reset it.")
            return

    # Only reached when the account does not exist, so a password is genuinely
    # needed. Prompting unconditionally and then discarding it on the promote
    # path would train people to type a password that does nothing.
    full_name = input("Full name: ").strip()
    password = _prompt_password()

    async with AsyncSessionLocal() as db:
        user = User(
            email=email,
            full_name=full_name or "Platform Admin",
            hashed_password=hash_password(password),
            role="admin",
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Created platform admin {user.email} (id {user.id}).")


def main() -> None:
    anyio.run(_bootstrap)


if __name__ == "__main__":
    main()
