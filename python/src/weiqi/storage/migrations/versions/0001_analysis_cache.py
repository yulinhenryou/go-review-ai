"""analysis cache: engine identities, engine queries and analysed positions (M3)

First drafted with Alembic's autogenerate from `weiqi.storage.schema`, then
edited by hand. `tests/storage/test_migrations.py` checks that it creates
exactly the tables the schema module describes.

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engine_identity",
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("model_sha256", sa.String(length=64), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("overrides", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("identity_key", name=op.f("pk_engine_identity")),
    )
    op.create_table(
        "engine_query",
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("elapsed_seconds", sa.Double(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_key"],
            ["engine_identity.identity_key"],
            name=op.f("fk_engine_query_identity_key_engine_identity"),
        ),
        sa.PrimaryKeyConstraint("query_id", name=op.f("pk_engine_query")),
    )
    op.create_index(op.f("ix_engine_query_identity_key"), "engine_query", ["identity_key"])
    op.create_table(
        "position_eval",
        sa.Column("query_key", sa.String(length=64), nullable=False),
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("stones_hash", sa.String(length=32), nullable=False),
        sa.Column("situation_hash", sa.String(length=32), nullable=False),
        sa.Column("current_player", sa.String(length=1), nullable=False),
        sa.Column("max_visits", sa.Integer(), nullable=False),
        sa.Column("root_visits", sa.Integer(), nullable=True),
        sa.Column("winrate_black", sa.Double(), nullable=True),
        sa.Column("score_lead_black", sa.Double(), nullable=True),
        sa.Column("candidates", sa.Text(), nullable=False),
        sa.Column("ownership", sa.LargeBinary(), nullable=True),
        sa.Column("engine_warnings", sa.Text(), nullable=False),
        sa.Column("encoding", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["query_id"],
            ["engine_query.query_id"],
            name=op.f("fk_position_eval_query_id_engine_query"),
        ),
        sa.PrimaryKeyConstraint("query_key", name=op.f("pk_position_eval")),
    )
    op.create_index(op.f("ix_position_eval_query_id"), "position_eval", ["query_id"])
    op.create_index(op.f("ix_position_eval_stones_hash"), "position_eval", ["stones_hash"])


def downgrade() -> None:
    op.drop_index(op.f("ix_position_eval_stones_hash"), table_name="position_eval")
    op.drop_index(op.f("ix_position_eval_query_id"), table_name="position_eval")
    op.drop_table("position_eval")
    op.drop_index(op.f("ix_engine_query_identity_key"), table_name="engine_query")
    op.drop_table("engine_query")
    op.drop_table("engine_identity")
