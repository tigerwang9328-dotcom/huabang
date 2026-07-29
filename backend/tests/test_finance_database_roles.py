import importlib
import importlib.util


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
