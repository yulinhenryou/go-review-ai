"""restricted searches: position_eval.allow_move (M4)

A search limited to one first move (KataGo `allowMoves`, used for the played
move, MIGRATION E04) is stored like any other turn under its own
`query_key`. This column records the move it was limited to, so the
position index never mistakes it for a free search. Existing rows are free
searches and keep `NULL`.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("position_eval") as batch:
        batch.add_column(sa.Column("allow_move", sa.String(length=8), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("position_eval") as batch:
        batch.drop_column("allow_move")
