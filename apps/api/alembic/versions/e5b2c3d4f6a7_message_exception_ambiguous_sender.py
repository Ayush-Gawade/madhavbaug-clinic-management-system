"""message exception ambiguous sender

Adds the ``ambiguous_sender`` reason so an inbound message whose sender matches
more than one patient is quarantined for staff review instead of being attached
to an arbitrary record (FR-010).

Revision ID: e5b2c3d4f6a7
Revises: d4a1b2c3e5f6
Create Date: 2026-10-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b2c3d4f6a7"
down_revision: str | None = "d4a1b2c3e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL requires enum values to be added outside the transaction that
    # first uses them, which this migration does not do.
    op.execute("ALTER TYPE exception_reason ADD VALUE IF NOT EXISTS 'ambiguous_sender'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value; removing it would require
    # recreating the type and rewriting dependent rows. Left as a no-op.
    pass
