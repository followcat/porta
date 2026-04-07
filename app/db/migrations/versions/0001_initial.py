"""Initial Porta schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "credentials",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("auth_type", sa.String(length=32), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_ciphertext", sa.LargeBinary(length=4096), nullable=True),
        sa.Column("password_nonce", sa.LargeBinary(length=64), nullable=True),
        sa.Column("password_tag", sa.LargeBinary(length=64), nullable=True),
        sa.Column("private_key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("private_key_nonce", sa.LargeBinary(length=64), nullable=True),
        sa.Column("private_key_tag", sa.LargeBinary(length=64), nullable=True),
        sa.Column("passphrase_ciphertext", sa.LargeBinary(length=4096), nullable=True),
        sa.Column("passphrase_nonce", sa.LargeBinary(length=64), nullable=True),
        sa.Column("passphrase_tag", sa.LargeBinary(length=64), nullable=True),
        sa.Column("key_version", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_credentials_name", "credentials", ["name"], unique=True)
    op.create_index("ix_credentials_auth_type", "credentials", ["auth_type"], unique=False)

    op.create_table(
        "tunnels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("ssh_host", sa.String(length=255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("credential_id", sa.BigInteger(), sa.ForeignKey("credentials.id"), nullable=False),
        sa.Column("bind_address", sa.String(length=64), nullable=False, server_default="127.0.0.1"),
        sa.Column("local_port", sa.Integer(), nullable=False),
        sa.Column("remote_host", sa.String(length=255), nullable=False),
        sa.Column("remote_port", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(length=128), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("auto_start", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("desired_state", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("restart_policy", sa.String(length=32), nullable=False, server_default="always"),
        sa.Column("restart_backoff_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("max_restart_backoff_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("max_retry_count", sa.Integer(), nullable=True),
        sa.Column("check_interval_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("healthcheck_type", sa.String(length=32), nullable=False, server_default="tcp"),
        sa.Column("healthcheck_path", sa.String(length=255), nullable=True),
        sa.Column("healthcheck_timeout_ms", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("healthcheck_interval_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("strict_host_key_checking", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("allow_gateway_ports", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("bind_address", "local_port", name="uk_bind_local_port"),
    )
    op.create_index("ix_tunnels_name", "tunnels", ["name"], unique=True)
    op.create_index("ix_tunnels_group_name", "tunnels", ["group_name"], unique=False)
    op.create_index("ix_tunnels_enabled", "tunnels", ["enabled"], unique=False)
    op.create_index("ix_tunnels_desired_state", "tunnels", ["desired_state"], unique=False)

    op.create_table(
        "tunnel_runtime",
        sa.Column("tunnel_id", sa.BigInteger(), sa.ForeignKey("tunnels.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("actual_state", sa.String(length=32), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("command_line", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_exit_at", sa.DateTime(), nullable=True),
        sa.Column("last_exit_code", sa.Integer(), nullable=True),
        sa.Column("restart_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("local_bind_ok", sa.Boolean(), nullable=True),
        sa.Column("healthcheck_ok", sa.Boolean(), nullable=True),
        sa.Column("last_healthcheck_at", sa.DateTime(), nullable=True),
        sa.Column("last_healthcheck_message", sa.Text(), nullable=True),
        sa.Column("current_error_code", sa.String(length=64), nullable=True),
        sa.Column("current_error_message", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "tunnel_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tunnel_id", sa.BigInteger(), sa.ForeignKey("tunnels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tunnel_events_tunnel_id", "tunnel_events", ["tunnel_id"], unique=False)
    op.create_index("ix_tunnel_events_event_type", "tunnel_events", ["event_type"], unique=False)
    op.create_index("ix_tunnel_events_created_at", "tunnel_events", ["created_at"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_tunnel_events_created_at", table_name="tunnel_events")
    op.drop_index("ix_tunnel_events_event_type", table_name="tunnel_events")
    op.drop_index("ix_tunnel_events_tunnel_id", table_name="tunnel_events")
    op.drop_table("tunnel_events")
    op.drop_table("tunnel_runtime")
    op.drop_index("ix_tunnels_desired_state", table_name="tunnels")
    op.drop_index("ix_tunnels_enabled", table_name="tunnels")
    op.drop_index("ix_tunnels_group_name", table_name="tunnels")
    op.drop_index("ix_tunnels_name", table_name="tunnels")
    op.drop_table("tunnels")
    op.drop_index("ix_credentials_auth_type", table_name="credentials")
    op.drop_index("ix_credentials_name", table_name="credentials")
    op.drop_table("credentials")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
