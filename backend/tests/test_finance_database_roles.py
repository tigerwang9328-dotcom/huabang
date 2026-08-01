import importlib
import importlib.util
from pathlib import Path


ROLE_BOOTSTRAP_SQL = (
    Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_finance_database_roles.sql"
)


def test_role_separation_rejects_history_writable_app_and_current_writable_importer():
    module_name = "scripts.verify_finance_database_roles"
    assert importlib.util.find_spec(module_name) is not None, "Phase 1 role verification script is missing"

    module = importlib.import_module(module_name)
    topology = module.FinanceRoleTopology(
        known_roles=set(module.REQUIRED_ROLES),
        schema_owners={
            "fin_current": "fin_schema_owner",
            "fin_history": "fin_schema_owner",
            "fin_read": "fin_schema_owner",
        },
        bypass_rls_roles=set(),
        schema_create_roles=set(),
        table_privileges={
            ("fin_app", "fin_history"): {"SELECT", "INSERT"},
            ("fin_history_importer", "fin_current"): {"SELECT", "UPDATE"},
        },
    )

    violations = module.validate_role_separation(topology)

    assert "fin_app must not write fin_history" in violations
    assert "fin_history_importer must not write fin_current" in violations


def test_role_separation_requires_non_owner_non_bypass_app_role():
    module_name = "scripts.verify_finance_database_roles"
    assert importlib.util.find_spec(module_name) is not None, "Phase 1 role verification script is missing"

    module = importlib.import_module(module_name)
    topology = module.FinanceRoleTopology(
        known_roles=set(module.REQUIRED_ROLES),
        schema_owners={
            "fin_current": "fin_app",
            "fin_history": "fin_schema_owner",
            "fin_read": "fin_schema_owner",
        },
        bypass_rls_roles={"fin_app"},
        schema_create_roles={"fin_app"},
        database_ddl_roles={"fin_app"},
        table_privileges={},
    )

    violations = module.validate_role_separation(topology)

    assert "fin_app must not own finance schemas" in violations
    assert "fin_app must not have BYPASSRLS" in violations
    assert "fin_app must not have CREATE on finance schemas" in violations
    assert "fin_app must not have database-level DDL capabilities" in violations


def test_role_separation_requires_dedicated_schema_owner_for_each_finance_schema():
    module_name = "scripts.verify_finance_database_roles"
    assert importlib.util.find_spec(module_name) is not None, "Phase 1 role verification script is missing"

    module = importlib.import_module(module_name)
    topology = module.FinanceRoleTopology(
        known_roles=set(module.REQUIRED_ROLES),
        schema_owners={
            "fin_current": "fin_migrator",
            "fin_history": "fin_schema_owner",
            "fin_read": "postgres",
        },
        bypass_rls_roles=set(),
        schema_create_roles=set(),
        database_ddl_roles=set(),
        table_privileges={},
    )

    violations = module.validate_role_separation(topology)

    assert "fin_current must be owned by fin_schema_owner" in violations
    assert "fin_read must be owned by fin_schema_owner" in violations


def test_role_separation_rejects_database_ddl_for_import_and_audit_roles():
    module_name = "scripts.verify_finance_database_roles"
    module = importlib.import_module(module_name)
    topology = module.FinanceRoleTopology(
        known_roles=set(module.REQUIRED_ROLES),
        schema_owners={schema: "fin_schema_owner" for schema in module.FINANCE_SCHEMAS},
        bypass_rls_roles=set(),
        schema_create_roles=set(),
        database_ddl_roles={"fin_history_importer", "fin_readonly_auditor"},
        table_privileges={},
    )

    violations = module.validate_role_separation(topology)

    assert "fin_history_importer must not have database-level DDL capabilities" in violations
    assert "fin_readonly_auditor must not have database-level DDL capabilities" in violations


def test_role_separation_rejects_owner_membership_for_restricted_roles():
    module_name = "scripts.verify_finance_database_roles"
    module = importlib.import_module(module_name)
    topology = module.FinanceRoleTopology(
        known_roles=set(module.REQUIRED_ROLES),
        schema_owners={schema: "fin_schema_owner" for schema in module.FINANCE_SCHEMAS},
        bypass_rls_roles=set(),
        schema_create_roles=set(),
        database_ddl_roles=set(),
        table_privileges={},
        role_memberships={
            "fin_app": {"fin_schema_owner"},
            "fin_history_importer": {"fin_schema_owner"},
            "fin_readonly_auditor": {"fin_schema_owner"},
        },
    )

    violations = module.validate_role_separation(topology)

    assert "fin_app must not be a member of fin_schema_owner" in violations
    assert "fin_history_importer must not be a member of fin_schema_owner" in violations
    assert "fin_readonly_auditor must not be a member of fin_schema_owner" in violations


def test_database_role_bootstrap_is_admin_only_and_denies_cross_schema_writes():
    script = ROLE_BOOTSTRAP_SQL.read_text(encoding="utf-8")

    assert "MUST be run by a PostgreSQL database administrator" in script
    for role in (
        "fin_schema_owner",
        "fin_migrator",
        "fin_app",
        "fin_history_importer",
        "fin_readonly_auditor",
    ):
        assert f"CREATE ROLE {role}" in script

    assert "ALTER SCHEMA fin_current OWNER TO fin_schema_owner" in script
    assert "ALTER SCHEMA fin_history OWNER TO fin_schema_owner" in script
    assert "ALTER SCHEMA fin_read OWNER TO fin_schema_owner" in script
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA fin_history FROM fin_app" in script
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA fin_current FROM fin_history_importer" in script
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA fin_read TO fin_app, fin_readonly_auditor" in script
    assert "existing Finance V2 objects are not owned by fin_schema_owner" in script
    assert "REVOKE fin_schema_owner FROM fin_app, fin_history_importer, fin_readonly_auditor" in script
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.alembic_version TO fin_schema_owner" in script


def test_database_role_verifier_collects_effective_not_only_direct_privileges():
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_finance_database_roles.py"
    source = script.read_text(encoding="utf-8")

    assert "has_table_privilege(role.oid, relation.oid, privilege.privilege_type)" in source
    assert "rolsuper" in source
    assert "pg_has_role(member.oid, owner.oid, 'MEMBER')" in source
