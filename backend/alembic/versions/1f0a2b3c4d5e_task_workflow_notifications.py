"""task workflow audit and DingTalk budget log

Revision ID: 1f0a2b3c4d5e
Revises: 1e0f1a2b3c4d
"""
from alembic import op

revision = "1f0a2b3c4d5e"
down_revision = "1e0f1a2b3c4d"
branch_labels = None
depends_on = None


TASK_PERMISSIONS = (
    ("task:view", "查看任务"),
    ("task:create", "创建任务"),
    ("task:approve", "确认派发任务"),
    ("task:feedback", "提交任务反馈"),
    ("task:review", "复查任务"),
    ("task:close", "关闭任务"),
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS app.task12_migration_task_backup (
            task_id bigint PRIMARY KEY,
            old_status varchar(32),
            old_role varchar(64),
            migrated_status varchar(32),
            migrated_role varchar(64)
        )
    """)
    op.execute("""
        INSERT INTO app.task12_migration_task_backup(task_id, old_status, old_role)
        SELECT id, status, assignee_role
        FROM app.app_action_task
        WHERE status='review_failed'
           OR assignee_role ~ '(operation|运营|商品经理|商品部|仓库主管|财务|会员运营|门店督导|导购|店长|督导)'
        ON CONFLICT (task_id) DO NOTHING
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS app.task12_migration_permission_backup (
            role_id bigint NOT NULL,
            permission_id bigint NOT NULL,
            PRIMARY KEY(role_id, permission_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS app.task12_migration_permission_meta_backup (
            code varchar(128) PRIMARY KEY,
            permission_id bigint,
            existed_before boolean NOT NULL,
            migration_created boolean NOT NULL DEFAULT false,
            old_name varchar(128),
            old_module varchar(64),
            old_description varchar(512),
            migrated_name varchar(128),
            migrated_module varchar(64),
            migrated_description varchar(512)
        )
    """)
    op.execute("""
        INSERT INTO app.task12_migration_permission_meta_backup(
            code, permission_id, existed_before, migration_created,
            old_name, old_module, old_description
        )
        SELECT wanted.code, permission.id, permission.id IS NOT NULL,
               permission.id IS NULL,
               permission.name, permission.module, permission.description
        FROM (VALUES
            ('task:view'), ('task:create'), ('task:approve'),
            ('task:feedback'), ('task:review'), ('task:close')
        ) AS wanted(code)
        LEFT JOIN sys.sys_permission permission ON permission.code=wanted.code
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS closed_by bigint")
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS closed_at timestamptz")
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS workflow_version integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_status varchar(32)")
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_error text")
    op.execute("ALTER TABLE app.app_action_task ADD COLUMN IF NOT EXISTS notification_updated_at timestamptz")
    op.execute("UPDATE app.app_action_task SET status='processing' WHERE status='review_failed'")
    op.execute("""
        UPDATE app.app_action_task
        SET assignee_role='operation_manager'
        WHERE assignee_role IN ('operation','运营','运营经理')
    """)
    op.execute("""
        UPDATE app.app_action_task
        SET assignee_role = replace(replace(replace(replace(replace(replace(replace(
            assignee_role,
            '商品经理','product_manager'),
            '商品部','product_manager'),
            '仓库主管','warehouse_manager'),
            '财务经理','finance_manager'),
            '会员运营','operation_manager'),
            '门店督导','area_supervisor'),
            '导购','guide')
        WHERE assignee_role IS NOT NULL
    """)
    op.execute("""
        UPDATE app.app_action_task
        SET assignee_role = replace(replace(replace(replace(replace(
            assignee_role,
            '运营经理','operation_manager'),
            '运营','operation_manager'),
            '财务','finance_manager'),
            '店长','store_manager'),
            '督导','area_supervisor')
        WHERE assignee_role IS NOT NULL
    """)
    op.execute("""
        UPDATE app.task12_migration_task_backup backup
        SET migrated_status=task.status, migrated_role=task.assignee_role
        FROM app.app_action_task task
        WHERE task.id=backup.task_id
    """)
    op.execute("ALTER TABLE app.app_action_task DROP CONSTRAINT IF EXISTS ck_action_task_workflow_status")
    op.execute("""
        ALTER TABLE app.app_action_task ADD CONSTRAINT ck_action_task_workflow_status
        CHECK (status IN ('draft','pending','processing','feedback_submitted','review_passed','overdue','closed','cancelled'))
    """)

    op.execute("ALTER TABLE app.app_task_feedback ADD COLUMN IF NOT EXISTS request_id varchar(64)")
    op.execute("ALTER TABLE app.app_task_review ADD COLUMN IF NOT EXISTS request_id varchar(64)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_task_feedback_request
        ON app.app_task_feedback(task_id, request_id) WHERE request_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_task_review_request
        ON app.app_task_review(task_id, request_id) WHERE request_id IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS log.log_dingtalk_api_call (
            id bigserial PRIMARY KEY,
            budget_date date NOT NULL,
            path varchar(256) NOT NULL,
            category varchar(64) NOT NULL,
            priority varchar(16) NOT NULL DEFAULT 'normal',
            status varchar(16) NOT NULL,
            used_after integer,
            error_message text,
            requested_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dingtalk_api_call_budget_date
        ON log.log_dingtalk_api_call(budget_date, category, requested_at DESC)
    """)

    for code, name in TASK_PERMISSIONS:
        escaped_name = name.replace("'", "''")
        op.execute(f"""
            INSERT INTO sys.sys_permission(code, name, module, description)
            VALUES ('{code}', '{escaped_name}', 'task', '任务闭环')
            ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, module='task', description='任务闭环'
        """)
    op.execute("""
        UPDATE app.task12_migration_permission_meta_backup backup
        SET permission_id=permission.id,
            migrated_name=permission.name,
            migrated_module=permission.module,
            migrated_description=permission.description
        FROM sys.sys_permission permission
        WHERE permission.code=backup.code
    """)
    op.execute("""
        INSERT INTO app.task12_migration_permission_backup(role_id, permission_id)
        SELECT r.id, p.id
        FROM sys.sys_role r
        CROSS JOIN sys.sys_permission p
        LEFT JOIN sys.sys_role_permission rp
          ON rp.role_id=r.id AND rp.permission_id=p.id
        WHERE (
            r.code IN ('super_admin','boss','ceo','area_supervisor','operation_manager')
            AND p.code IN ('task:view','task:create','task:approve','task:feedback','task:review','task:close')
        ) OR (
            r.code IN (
                'product_manager','product_specialist','finance_manager','accountant',
                'cashier','warehouse_manager','store_manager','guide'
            )
            AND p.code IN ('task:view','task:feedback')
        )
        ON CONFLICT (role_id, permission_id) DO NOTHING
    """)
    op.execute("""
        DELETE FROM app.task12_migration_permission_backup backup
        USING sys.sys_role_permission existing
        WHERE existing.role_id=backup.role_id
          AND existing.permission_id=backup.permission_id
    """)
    op.execute("""
        INSERT INTO sys.sys_role_permission(role_id, permission_id)
        SELECT r.id, p.id FROM sys.sys_role r CROSS JOIN sys.sys_permission p
        WHERE r.code IN ('super_admin','boss','ceo','area_supervisor','operation_manager')
          AND p.code IN ('task:view','task:create','task:approve','task:feedback','task:review','task:close')
        ON CONFLICT (role_id, permission_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO sys.sys_role_permission(role_id, permission_id)
        SELECT r.id, p.id FROM sys.sys_role r CROSS JOIN sys.sys_permission p
        WHERE r.code IN (
            'product_manager','product_specialist','finance_manager','accountant',
            'cashier','warehouse_manager','store_manager','guide'
        )
          AND p.code IN ('task:view','task:feedback')
        ON CONFLICT (role_id, permission_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE app.app_action_task DROP CONSTRAINT IF EXISTS ck_action_task_workflow_status")
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('app.task12_migration_task_backup') IS NOT NULL THEN
                UPDATE app.app_action_task task
                SET status=backup.old_status
                FROM app.task12_migration_task_backup backup
                WHERE task.id=backup.task_id
                  AND backup.old_status IS DISTINCT FROM backup.migrated_status
                  AND task.status=backup.migrated_status;
                UPDATE app.app_action_task task
                SET assignee_role=backup.old_role
                FROM app.task12_migration_task_backup backup
                WHERE task.id=backup.task_id
                  AND backup.old_role IS DISTINCT FROM backup.migrated_role
                  AND task.assignee_role IS NOT DISTINCT FROM backup.migrated_role;
            END IF;
            IF to_regclass('app.task12_migration_permission_backup') IS NOT NULL THEN
                DELETE FROM sys.sys_role_permission grant_row
                USING app.task12_migration_permission_backup backup
                WHERE grant_row.role_id=backup.role_id
                  AND grant_row.permission_id=backup.permission_id;
            END IF;
        END $$
    """)
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('app.task12_migration_permission_meta_backup') IS NOT NULL THEN
                UPDATE sys.sys_permission permission
                SET name=backup.old_name,
                    module=backup.old_module,
                    description=backup.old_description
                FROM app.task12_migration_permission_meta_backup backup
                WHERE backup.existed_before=true
                  AND permission.id=backup.permission_id
                  AND permission.name IS NOT DISTINCT FROM backup.migrated_name
                  AND permission.module IS NOT DISTINCT FROM backup.migrated_module
                  AND permission.description IS NOT DISTINCT FROM backup.migrated_description;

                DELETE FROM sys.sys_permission permission
                USING app.task12_migration_permission_meta_backup backup
                WHERE backup.migration_created=true
                  AND permission.id=backup.permission_id
                  AND permission.name IS NOT DISTINCT FROM backup.migrated_name
                  AND permission.module IS NOT DISTINCT FROM backup.migrated_module
                  AND permission.description IS NOT DISTINCT FROM backup.migrated_description
                  AND NOT EXISTS (
                      SELECT 1 FROM sys.sys_role_permission role_permission
                      WHERE role_permission.permission_id=permission.id
                  );
            END IF;
        END $$
    """)
    op.execute("DROP INDEX IF EXISTS log.idx_dingtalk_api_call_budget_date")
    op.execute("DROP TABLE IF EXISTS log.log_dingtalk_api_call")
    op.execute("DROP INDEX IF EXISTS app.uq_task_review_request")
    op.execute("DROP INDEX IF EXISTS app.uq_task_feedback_request")
    op.execute("ALTER TABLE app.app_task_review DROP COLUMN IF EXISTS request_id")
    op.execute("ALTER TABLE app.app_task_feedback DROP COLUMN IF EXISTS request_id")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_updated_at")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_error")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS notification_status")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS workflow_version")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS closed_at")
    op.execute("ALTER TABLE app.app_action_task DROP COLUMN IF EXISTS closed_by")
    op.execute("DROP TABLE IF EXISTS app.task12_migration_permission_meta_backup")
    op.execute("DROP TABLE IF EXISTS app.task12_migration_permission_backup")
    op.execute("DROP TABLE IF EXISTS app.task12_migration_task_backup")
