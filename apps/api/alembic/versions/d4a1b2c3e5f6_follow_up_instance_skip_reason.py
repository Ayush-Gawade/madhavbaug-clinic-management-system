"""follow up instance skip reason

Records why a follow-up instance was cancelled (consent withdrawn, patient
inactive, schedule no longer active, or resolved by staff) so the reason is
auditable at send time (FR-010, FR-027).

Revision ID: d4a1b2c3e5f6
Revises: c3f5a7b2d841
Create Date: 2026-10-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a1b2c3e5f6"
down_revision: str | None = "c3f5a7b2d841"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "follow_up_instances",
        sa.Column("skip_reason", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("follow_up_instances", "skip_reason")
