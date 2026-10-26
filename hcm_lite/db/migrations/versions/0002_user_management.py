"""user management: email login + admin role + user-admin audit actions

Adds ``users.email`` (NOT NULL, UNIQUE), widens the ``users.role`` CHECK to allow ``admin``,
and widens the ``audit_events.action`` CHECK with the user-administration actions. Portable for
SQLite and PostgreSQL: ``op.batch_alter_table`` rebuilds the table on SQLite (where a CHECK
cannot be altered in place) and issues direct ALTER statements on PostgreSQL.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROLES_NEW = "role IN ('employee', 'manager', 'hr_admin', 'admin')"
_ROLES_OLD = "role IN ('employee', 'manager', 'hr_admin')"

_ACTIONS_NEW = (
    "action IN ('login_success', 'login_failed', 'account_locked', 'logout', "
    "'session_expired', 'access_denied', 'leave_submitted', 'password_changed', "
    "'user_created', 'user_updated', 'user_deactivated', 'user_activated', "
    "'user_deleted', 'admin_created')"
)
_ACTIONS_OLD = (
    "action IN ('login_success', 'login_failed', 'account_locked', 'logout', "
    "'session_expired', 'access_denied', 'leave_submitted')"
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        # A temporary server_default lets existing rows satisfy NOT NULL during the add.
        batch_op.add_column(
            sa.Column("email", sa.String(length=255), nullable=False, server_default="")
        )
        batch_op.create_unique_constraint(op.f("uq_users_email"), ["email"])
        batch_op.drop_constraint(op.f("ck_users_role"), type_="check")
        batch_op.create_check_constraint(op.f("ck_users_role"), _ROLES_NEW)
    # Drop the temporary default so future inserts must provide an explicit email.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("email", server_default=None)

    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_audit_events_action"), type_="check")
        batch_op.create_check_constraint(op.f("ck_audit_events_action"), _ACTIONS_NEW)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_audit_events_action"), type_="check")
        batch_op.create_check_constraint(op.f("ck_audit_events_action"), _ACTIONS_OLD)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_users_role"), type_="check")
        batch_op.create_check_constraint(op.f("ck_users_role"), _ROLES_OLD)
        batch_op.drop_constraint(op.f("uq_users_email"), type_="unique")
        batch_op.drop_column("email")
