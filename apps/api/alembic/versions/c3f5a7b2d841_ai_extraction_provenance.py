"""ai extraction provenance

Revision ID: c3f5a7b2d841
Revises: b7c1e2f4a9d0
Create Date: 2026-10-10 03:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3f5a7b2d841"
down_revision: str | None = "b7c1e2f4a9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_extractions",
        sa.Column("patient_id", sa.UUID(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column(
            "modality",
            sa.Enum("text", "vision", name="ai_extraction_modality"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "succeeded",
                "needs_clarification",
                "skipped",
                "failed",
                name="ai_extraction_status",
            ),
            nullable=False,
        ),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("needs_clarification", sa.Boolean(), nullable=False),
        sa.Column("clarification_question", sa.Text(), nullable=True),
        sa.Column("extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("observations_created", sa.Integer(), nullable=False),
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
            name=op.f("fk_ai_extractions_patient_id_patients"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["whatsapp_messages.id"],
            name=op.f("fk_ai_extractions_message_id_whatsapp_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_extractions")),
    )
    op.create_index("ix_ai_extractions_patient", "ai_extractions", ["patient_id"], unique=False)
    op.create_index("ix_ai_extractions_message", "ai_extractions", ["message_id"], unique=False)
    op.create_index("ix_ai_extractions_status", "ai_extractions", ["status"], unique=False)

    op.add_column("observations", sa.Column("ai_extraction_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_observations_ai_extraction_id_ai_extractions"),
        "observations",
        "ai_extractions",
        ["ai_extraction_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_observations_ai_extraction_id_ai_extractions"),
        "observations",
        type_="foreignkey",
    )
    op.drop_column("observations", "ai_extraction_id")
    op.drop_index("ix_ai_extractions_status", table_name="ai_extractions")
    op.drop_index("ix_ai_extractions_message", table_name="ai_extractions")
    op.drop_index("ix_ai_extractions_patient", table_name="ai_extractions")
    op.drop_table("ai_extractions")
    for enum_name in ("ai_extraction_status", "ai_extraction_modality"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
