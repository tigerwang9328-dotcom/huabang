"""add boss ai assistant conversations

Revision ID: 299f6a7b8c92
Revises: 288f6a7b8c91
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "299f6a7b8c92"
down_revision = "288f6a7b8c91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ai")
    op.create_table(
        "ai_assistant_conversation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False, server_default="新对话"),
        sa.Column("route", sa.String(length=256), nullable=True),
        sa.Column("stat_date", sa.Date(), nullable=True),
        sa.Column("store_code", sa.String(length=64), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="ai",
    )
    op.create_index(
        "ix_ai_assistant_conversation_user_last",
        "ai_assistant_conversation",
        ["user_id", "is_archived", "last_message_at"],
        schema="ai",
    )
    op.create_table(
        "ai_assistant_message",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("answer_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("used_web", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai.ai_assistant_conversation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="ai",
    )
    op.create_index(
        "ix_ai_assistant_message_conversation_created",
        "ai_assistant_message",
        ["conversation_id", "created_at"],
        schema="ai",
    )


def downgrade() -> None:
    op.drop_index("ix_ai_assistant_message_conversation_created", table_name="ai_assistant_message", schema="ai")
    op.drop_table("ai_assistant_message", schema="ai")
    op.drop_index("ix_ai_assistant_conversation_user_last", table_name="ai_assistant_conversation", schema="ai")
    op.drop_table("ai_assistant_conversation", schema="ai")
