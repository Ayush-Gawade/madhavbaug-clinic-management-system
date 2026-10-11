"""rule engine and alerts

Revision ID: b7c1e2f4a9d0
Revises: 639bd8aae61c
Create Date: 2026-10-10 02:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7c1e2f4a9d0"
down_revision: str | None = "639bd8aae61c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "safety_rules",
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "metric",
            sa.Enum("blood_glucose", "weight", "systolic", "diastolic", name="rule_metric"),
            nullable=False,
        ),
        sa.Column(
            "comparator",
            sa.Enum("gt", "gte", "lt", "lte", name="rule_comparator"),
            nullable=False,
        ),
        sa.Column("threshold", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column(
            "priority",
            sa.Enum("routine", "priority", "urgent", name="alert_priority"),
            nullable=False,
        ),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_safety_rules_created_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_safety_rules")),
        sa.UniqueConstraint("rule_key", "version", name="uq_safety_rules_rule_key_version"),
    )
    op.create_index("ix_safety_rules_metric", "safety_rules", ["metric"], unique=False)
    op.create_index("ix_safety_rules_active", "safety_rules", ["is_active"], unique=False)

    op.create_table(
        "alerts",
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("observation_id", sa.UUID(), nullable=True),
        sa.Column("follow_up_instance_id", sa.UUID(), nullable=True),
        sa.Column("rule_id", sa.UUID(), nullable=True),
        sa.Column("rule_version", sa.Integer(), nullable=True),
        sa.Column("metric", sa.String(length=20), nullable=True),
        sa.Column("value", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column(
            "alert_type",
            sa.Enum(
                "threshold",
                "non_response",
                "delivery_failure",
                "clarification",
                "manual",
                name="alert_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("routine", "priority", "urgent", name="alert_priority"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("open", "acknowledged", "resolved", "dismissed", name="alert_status"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("assigned_to", sa.UUID(), nullable=True),
        sa.Column("acknowledged_by", sa.UUID(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
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
            ["patient_id"], ["patients.id"], name=op.f("fk_alerts_patient_id_patients"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["observations.id"],
            name=op.f("fk_alerts_observation_id_observations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["follow_up_instance_id"],
            ["follow_up_instances.id"],
            name=op.f("fk_alerts_follow_up_instance_id_follow_up_instances"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["safety_rules.id"], name=op.f("fk_alerts_rule_id_safety_rules"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"], ["staff_users.id"], name=op.f("fk_alerts_assigned_to_staff_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["staff_users.id"],
            name=op.f("fk_alerts_acknowledged_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["staff_users.id"], name=op.f("fk_alerts_resolved_by_staff_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index("ix_alerts_status", "alerts", ["status"], unique=False)
    op.create_index("ix_alerts_priority", "alerts", ["priority"], unique=False)
    op.create_index("ix_alerts_patient", "alerts", ["patient_id"], unique=False)
    op.create_index("ix_alerts_created", "alerts", ["created_at"], unique=False)

    op.create_table(
        "clinician_actions",
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=True),
        sa.Column(
            "action_type",
            sa.Enum(
                "acknowledge",
                "assign",
                "escalate",
                "resolve",
                "dismiss",
                "comment",
                name="clinician_action_type",
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            ["alert_id"], ["alerts.id"], name=op.f("fk_clinician_actions_alert_id_alerts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f("fk_clinician_actions_patient_id_patients"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["staff_users.id"], name=op.f("fk_clinician_actions_actor_id_staff_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinician_actions")),
    )
    op.create_index(
        "ix_clinician_actions_alert", "clinician_actions", ["alert_id"], unique=False
    )

    # Seed the demonstrator thresholds (PRD FR-019). These are preliminary
    # examples only and are expected to be replaced by clinic-approved rules.
    op.execute(
        """
        INSERT INTO safety_rules
            (id, rule_key, version, metric, comparator, threshold, unit, priority,
             context, description, is_active, created_by, created_at, updated_at)
        VALUES
            (gen_random_uuid(), 'bp_systolic_high', 1, 'systolic', 'gt', 140, 'mmHg',
             'urgent', NULL, 'Systolic blood pressure above 140 mmHg', true, NULL, now(), now()),
            (gen_random_uuid(), 'bp_systolic_low', 1, 'systolic', 'lt', 100, 'mmHg',
             'urgent', NULL, 'Systolic blood pressure below 100 mmHg', true, NULL, now(), now()),
            (gen_random_uuid(), 'glucose_high', 1, 'blood_glucose', 'gt', 200, 'mg/dL',
             'priority', NULL, 'Blood glucose above 200 mg/dL', true, NULL, now(), now()),
            (gen_random_uuid(), 'glucose_low', 1, 'blood_glucose', 'lt', 60, 'mg/dL',
             'urgent', NULL, 'Blood glucose below 60 mg/dL', true, NULL, now(), now())
        """
    )


def downgrade() -> None:
    op.drop_index("ix_clinician_actions_alert", table_name="clinician_actions")
    op.drop_table("clinician_actions")
    op.drop_index("ix_alerts_created", table_name="alerts")
    op.drop_index("ix_alerts_patient", table_name="alerts")
    op.drop_index("ix_alerts_priority", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_safety_rules_active", table_name="safety_rules")
    op.drop_index("ix_safety_rules_metric", table_name="safety_rules")
    op.drop_table("safety_rules")
    for enum_name in (
        "clinician_action_type",
        "alert_status",
        "alert_type",
        "alert_priority",
        "rule_comparator",
        "rule_metric",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
