"""initial

Revision ID: b1063dff81db
Revises:
Create Date: 2026-04-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1063dff81db"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("service", sa.String(255), nullable=False),
        sa.Column("group", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("labels", sa.JSON, nullable=True),
        sa.Column("suppressed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_routed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("routing_result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_service", "alerts", ["service"])
    op.create_index("ix_alerts_group", "alerts", ["group"])
    op.create_index("ix_alerts_suppressed", "alerts", ["suppressed"])
    op.create_index("ix_alerts_is_routed", "alerts", ["is_routed"])

    op.create_table(
        "routing_configs",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("conditions", sa.JSON, nullable=False),
        sa.Column("target", sa.JSON, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("suppression_window_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("active_hours", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_routing_configs_priority", "routing_configs", ["priority"])

    op.create_table(
        "route_suppressions",
        sa.Column("route_id", sa.String(255), primary_key=True),
        sa.Column("service", sa.String(255), primary_key=True),
        sa.Column("last_routed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("route_suppressions")
    op.drop_index("ix_routing_configs_priority", table_name="routing_configs")
    op.drop_table("routing_configs")
    op.drop_index("ix_alerts_is_routed", table_name="alerts")
    op.drop_index("ix_alerts_suppressed", table_name="alerts")
    op.drop_index("ix_alerts_group", table_name="alerts")
    op.drop_index("ix_alerts_service", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_table("alerts")
