"""system settings rbac security hardening

Revision ID: 9a1b2c3d4e5f
Revises: c7d8e9f0a1b2
Create Date: 2026-07-09
"""
from alembic import op

revision = "9a1b2c3d4e5f"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""CREATE TABLE IF NOT EXISTS sys.sys_register_application (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), username varchar(64) NOT NULL, password_hash varchar(255) NOT NULL, real_name varchar(64) NOT NULL, phone varchar(32) NOT NULL, apply_role varchar(64) NOT NULL, department varchar(128), store_code varchar(64), remark text, status varchar(32) NOT NULL DEFAULT 'pending', client_ip varchar(64), created_at timestamptz NOT NULL DEFAULT now(), reviewed_by bigint, reviewed_at timestamptz, reject_reason text, approved_user_id bigint, review_note text, assigned_role_ids jsonb, assigned_store_codes jsonb, assigned_dept_id bigint)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sys_register_application_username ON sys.sys_register_application(username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sys_register_application_phone ON sys.sys_register_application(phone)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sys_register_application_status ON sys.sys_register_application(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sys_register_application_created_at ON sys.sys_register_application(created_at)")
    op.execute("""CREATE TABLE IF NOT EXISTS sys.sys_operation_log (id bigserial PRIMARY KEY, user_id bigint, username varchar(64), module varchar(64) NOT NULL, action varchar(64) NOT NULL, target_type varchar(64), target_id varchar(128), before_data jsonb, after_data jsonb, ip varchar(64), user_agent text, created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sys_operation_log_module_action ON sys.sys_operation_log(module, action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sys_operation_log_username ON sys.sys_operation_log(username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sys_operation_log_created_at ON sys.sys_operation_log(created_at)")
    op.execute("ALTER TABLE sys.sys_role ADD COLUMN IF NOT EXISTS is_builtin boolean DEFAULT false")
    op.execute("ALTER TABLE sys.sys_role ADD COLUMN IF NOT EXISTS is_legacy boolean DEFAULT false")
    op.execute("ALTER TABLE sys.sys_role ADD COLUMN IF NOT EXISTS is_hidden boolean DEFAULT false")
    op.execute("ALTER TABLE sys.sys_user ADD COLUMN IF NOT EXISTS employee_no varchar(64)")
    op.execute("ALTER TABLE sys.sys_user ADD COLUMN IF NOT EXISTS position varchar(64)")
    op.execute("ALTER TABLE sys.sys_user ADD COLUMN IF NOT EXISTS failed_login_count integer DEFAULT 0")
    op.execute("ALTER TABLE sys.sys_user ADD COLUMN IF NOT EXISTS locked_until timestamptz")
    op.execute("""CREATE TABLE IF NOT EXISTS sys.sys_user_store (id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES sys.sys_user(id), store_code varchar(64) NOT NULL, store_name varchar(128), is_primary boolean DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(user_id, store_code))""")

def downgrade():
    op.execute("DROP TABLE IF EXISTS sys.sys_user_store")
    op.execute("ALTER TABLE sys.sys_user DROP COLUMN IF EXISTS locked_until")
    op.execute("ALTER TABLE sys.sys_user DROP COLUMN IF EXISTS failed_login_count")
    op.execute("ALTER TABLE sys.sys_user DROP COLUMN IF EXISTS position")
    op.execute("ALTER TABLE sys.sys_user DROP COLUMN IF EXISTS employee_no")
    op.execute("ALTER TABLE sys.sys_role DROP COLUMN IF EXISTS is_hidden")
    op.execute("ALTER TABLE sys.sys_role DROP COLUMN IF EXISTS is_legacy")
    op.execute("ALTER TABLE sys.sys_role DROP COLUMN IF EXISTS is_builtin")
    op.execute("DROP TABLE IF EXISTS sys.sys_operation_log")
    op.execute("DROP TABLE IF EXISTS sys.sys_register_application")
