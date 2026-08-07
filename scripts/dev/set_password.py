"""Dev utility: set a user's password from the terminal.

The platform has no password-reset endpoint, so an account whose password is
unknown can only be recovered by writing a new hash directly.

Deliberately kept OUTSIDE `backend/`. The backend image is built with
`context: ./backend` and a `COPY . .`, so a file placed there ships to every
deployment — including production — and this script changes a credential.
Living at the repo root means it is physically absent from the image rather
than merely excluded by a rule someone could later "tidy up". The repo is
already bind-mounted at /repo in the dev containers, so it still runs:

    docker exec -it stlc_backend python /repo/scripts/dev/set_password.py

Safety properties:
  - Refuses to run unless APP_ENV is "local" (see `_require_local_environment`).
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
import os
import sys

# Running this by path — `python /repo/scripts/dev/set_password.py` — puts THIS
# file's directory on sys.path, not the backend package root, so `app` is not
# importable and the script dies on the first import below. The working
# directory is not consulted for that when a script path is given. The backend
# image sets WORKDIR /app and compose bind-mounts ./backend there, so add it
# explicitly rather than depending on the caller exporting PYTHONPATH.
_BACKEND_ROOT = os.environ.get("BACKEND_ROOT", "/app")
if os.path.isdir(os.path.join(_BACKEND_ROOT, "app")) and _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import anyio
from sqlalchemy import func, select

from app.config import get_settings
from app.core.password_validation import validate_password_strength
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.user import User

# bcrypt silently truncates beyond 72 bytes, so a longer password would not be
# the password the user thinks they set.
_MAX_PASSWORD_BYTES = 72


def _require_local_environment() -> None:
    settings = get_settings()
    if settings.app_env != "local":
        print(f"Refusing to run: APP_ENV is {settings.app_env!r}, not 'local'.")
        print("This tool changes a credential without an audit record and is for local development only.")
        sys.exit(1)


async def _set_password(email: str, password: str) -> None:
    async with AsyncSessionLocal() as db:
        # Case-insensitive lookup: `create_user` historically stored the address
        # as typed, so a row may exist with different capitalisation than the
        # one login would search for.
        result = await db.execute(select(User).where(func.lower(User.email) == email))
        users = list(result.scalars().all())

        if not users:
            print(f"No user found with email {email!r}.")
            sys.exit(1)
        if len(users) > 1:
            print(f"{len(users)} accounts share this address, differing only in case:")
            for user in users:
                print(f"  id {user.id}: {user.email!r} (role {user.role}, active {user.is_active})")
            print("Refusing to guess which one you meant — resolve the duplicates first.")
            sys.exit(1)

        user = users[0]
        user.hashed_password = hash_password(password)
        await db.commit()
        print(f"Password updated for {user.email} (id {user.id}, role {user.role}).")


def main() -> None:
    _require_local_environment()

    raw_email = input("Email: ").strip()
    # Login lowercases the address before looking it up, so normalise here too.
    email = raw_email.lower()
    if email != raw_email:
        print(f"Normalised to {email}")

    password = getpass.getpass("New password: ")
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

    anyio.run(_set_password, email, password)


if __name__ == "__main__":
    main()
