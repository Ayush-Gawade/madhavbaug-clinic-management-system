"""Command-line utilities: ``python -m app.cli <command>``."""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.user import StaffRole
from app.schemas.auth import StaffUserCreate
from app.services import users as users_service


async def seed() -> None:
    """Create the bootstrap administrator if no matching account exists."""
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        existing = await users_service.get_by_email(db, settings.bootstrap_admin_email)
        if existing is not None:
            print(f"Bootstrap admin already present: {existing.email}")
            return
        admin = await users_service.create_user(
            db,
            StaffUserCreate(
                email=settings.bootstrap_admin_email,
                full_name=settings.bootstrap_admin_name,
                role=StaffRole.OWNER,
                password=settings.bootstrap_admin_password,
            ),
        )
        await db.commit()
        print(f"Created bootstrap admin: {admin.email} ({admin.role.value})")


COMMANDS = {"seed": seed}


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli", description="Madhavbaug admin CLI")
    parser.add_argument("command", choices=sorted(COMMANDS), help="Command to run")
    args = parser.parse_args()
    asyncio.run(COMMANDS[args.command]())


if __name__ == "__main__":
    main()
