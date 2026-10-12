"""follow-up schedule free-form message body

Adds an optional ``message_body`` column to ``follow_up_schedules`` so a
schedule without a template can carry the staff-authored free-form text
(FR "free-form text box" in the Message Scheduler). Dispatch prefers the
template body when a template is set and falls back to this text.

Revision ID: 6f1a2b3c4d5e
Revises: e5b2c3d4f6a7
Create Date: 2026-10-12 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f1a2b3c4d5e"
down_revision: str | None = "e5b2c3d4f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("follow_up_schedules", sa.Column("message_body", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("follow_up_schedules", "message_body")