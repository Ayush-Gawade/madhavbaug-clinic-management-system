"""runtime settings and auto-reply provenance

Adds the two tables the AI auto-reply feature depends on:

* ``app_settings`` — a curated key/value store so a clinician can switch the
  auto-reply feature on or off (and point urgent notifications at a doctor's
  WhatsApp number) from the Settings screen instead of editing ``.env``.
* ``auto_replies`` — one row per inbound message the auto-reply decided about,
  keyed UNIQUE on ``source_message_id`` so a retried worker or a re-analysis can
  never send a patient the same reply twice.

Both settings rows are seeded disabled-by-default: nothing sends until a
clinician turns it on.

Revision ID: d4e5f6a7b8c9
Revises: 6f1a2b3c4d5e
Create Date: 2026-10-19 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "6f1a2b3c4d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENABLED_DESCRIPTION = (
    "Let the assistant reply to patient WhatsApp messages automatically. "
    "Requires AI extraction to be enabled."
)
DOCTOR_PHONE_DESCRIPTION = "Doctor's WhatsApp number notified when a critical reading arrives."


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["staff_users.id"],
            name="fk_app_settings_updated_by_staff_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_settings"),
        sa.UniqueConstraint("key", name="uq_app_settings_key"),
    )

    op.create_table(
        "auto_replies",
        sa.Column("source_message_id", sa.UUID(), nullable=False),
        sa.Column("reply_message_id", sa.UUID(), nullable=True),
        sa.Column("patient_id", sa.UUID(), nullable=True),
        sa.Column(
            "mode",
            sa.Enum(
                "safe_reading",
                "out_of_range_reading",
                "clarification",
                name="auto_reply_mode",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                "suppressed",
                name="auto_reply_status",
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("generated_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("doctor_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name="fk_auto_replies_patient_id_patients",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reply_message_id"],
            ["whatsapp_messages.id"],
            name="fk_auto_replies_reply_message_id_whatsapp_messages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["whatsapp_messages.id"],
            name="fk_auto_replies_source_message_id_whatsapp_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auto_replies"),
        sa.UniqueConstraint("source_message_id", name="uq_auto_replies_source_message_id"),
    )
    op.create_index("ix_auto_replies_patient", "auto_replies", ["patient_id"], unique=False)
    op.create_index("ix_auto_replies_status", "auto_replies", ["status"], unique=False)

    settings = sa.table(
        "app_settings",
        sa.column("id", sa.UUID()),
        sa.column("key", sa.String(length=64)),
        sa.column("value", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("description", sa.String(length=255)),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": uuid.uuid4(),
                "key": "ai_autoreply_enabled",
                "value": False,
                "description": ENABLED_DESCRIPTION,
            },
            {
                "id": uuid.uuid4(),
                "key": "ai_autoreply_doctor_phone",
                "value": "+919359883349",
                "description": DOCTOR_PHONE_DESCRIPTION,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_auto_replies_status", table_name="auto_replies")
    op.drop_index("ix_auto_replies_patient", table_name="auto_replies")
    op.drop_table("auto_replies")
    for enum_name in ("auto_reply_status", "auto_reply_mode"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    op.drop_table("app_settings")
