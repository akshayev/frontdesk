"""Seed holidays: only 2026-12-25 and 2027-01-26 (D-014). Others are added by the lead.

Revision ID: 0004_seed_holidays
Revises: 0003_app_role
Create Date: 2026-11-22
"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa

from alembic import op

revision: str = "0004_seed_holidays"
down_revision: str | None = "0003_app_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED = (
    {"d": date(2026, 12, 25), "n": "Christmas"},
    {"d": date(2027, 1, 26), "n": "Republic Day"},
)


def upgrade() -> None:
    """Insert the two seeded holidays (created_by NULL = seeded by migration)."""
    op.get_bind().execute(
        sa.text("INSERT INTO holidays (date, name) VALUES (:d, :n)"), list(SEED)
    )


def downgrade() -> None:
    """Remove exactly the seeded rows."""
    op.get_bind().execute(sa.text("DELETE FROM holidays WHERE date = :d"), list(SEED))
