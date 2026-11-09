"""reviews: games, review runs and per-move metrics (M4)

A review stores the uploaded SGF once per file content (`game`, unique by
SHA-256), each review of it with its settings and full result (`review_run`),
and one row per move and score-loss definition (`move_metric`) for SQL
aggregation in later milestones.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game",
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("sgf_sha256", sa.String(length=64), nullable=False),
        sa.Column("sgf", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("game_id", name=op.f("pk_game")),
        sa.UniqueConstraint("sgf_sha256", name=op.f("uq_game_sgf_sha256")),
    )
    op.create_table(
        "review_run",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("rules", sa.String(length=20), nullable=False),
        sa.Column("komi", sa.Double(), nullable=False),
        sa.Column("settings", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["game.game_id"], name=op.f("fk_review_run_game_id_game")
        ),
        sa.ForeignKeyConstraint(
            ["identity_key"],
            ["engine_identity.identity_key"],
            name=op.f("fk_review_run_identity_key_engine_identity"),
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_review_run")),
    )
    op.create_index(op.f("ix_review_run_game_id"), "review_run", ["game_id"])
    op.create_table(
        "move_metric",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("move_number", sa.Integer(), nullable=False),
        sa.Column("definition", sa.String(length=40), nullable=False),
        sa.Column("color", sa.String(length=1), nullable=False),
        sa.Column("raw_score_loss", sa.Double(), nullable=True),
        sa.Column("score_loss", sa.Double(), nullable=True),
        sa.Column("winrate_delta_pp", sa.Double(), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=True),
        sa.Column("flags", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["review_run.run_id"], name=op.f("fk_move_metric_run_id_review_run")
        ),
        sa.PrimaryKeyConstraint("run_id", "move_number", "definition", name=op.f("pk_move_metric")),
    )
    op.create_index("ix_move_metric_definition_severity", "move_metric", ["definition", "severity"])


def downgrade() -> None:
    op.drop_index("ix_move_metric_definition_severity", table_name="move_metric")
    op.drop_table("move_metric")
    op.drop_index(op.f("ix_review_run_game_id"), table_name="review_run")
    op.drop_table("review_run")
    op.drop_table("game")
