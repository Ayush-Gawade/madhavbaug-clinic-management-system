"""widen app_settings.description to TEXT

Registry descriptions are prose written in code, and the ``ai_autoreply_doctor_template``
setting's help text pushed past ``VARCHAR(255)`` -- which surfaced only as a
500 when a clinician saved the Settings screen.

The column is a write-only snapshot: every read serves ``spec.description``
from the curated registry, so widening it changes no behaviour and only removes
the ceiling on how much documentation a setting may carry.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "app_settings",
        "description",
        type_=sa.Text(),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Fails loudly if any stored description now exceeds 255 characters, which
    # is the honest outcome: the narrower column cannot hold what was written.
    op.alter_column(
        "app_settings",
        "description",
        type_=sa.String(length=255),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
