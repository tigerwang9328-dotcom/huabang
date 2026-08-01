"""Read-only verifier for Finance V2 database-role separation.

The verifier deliberately does not create roles or change grants.  A non-zero
exit means the database cannot satisfy the Finance V2 write gate yet.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Mapping, Set, Tuple


FINANCE_SCHEMAS = frozenset({"fin_current", "fin_history", "fin_read"})
WRITE_PRIVILEGES = frozenset({"INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"})
REQUIRED_ROLES = frozenset(
    {
        "fin_schema_owner",
        "fin_migrator",
        "fin_app",
        "fin_history_importer",
        "fin_readonly_auditor",
    }
)


@dataclass(frozen=True)
class FinanceRoleTopology:
    """Database authorization facts needed for the Finance V2 release gate."""

    known_roles: Set[str] = field(default_factory=set)
    schema_owners: Mapping[str, str] = field(default_factory=dict)
    bypass_rls_roles: Set[str] = field(default_factory=set)
    schema_create_roles: Set[str] = field(default_factory=set)
    database_ddl_roles: Set[str] = field(default_factory=set)
    table_privileges: Mapping[Tuple[str, str], Set[str]] = field(default_factory=dict)
    role_memberships: Mapping[str, Set[str]] = field(default_factory=dict)


def _has_write_privilege(topology: FinanceRoleTopology, role: str, schema: str) -> bool:
    privileges = topology.table_privileges.get((role, schema), set())
    return bool(WRITE_PRIVILEGES.intersection(privileges))


def validate_role_separation(topology: FinanceRoleTopology) -> list[str]:
    """Return every authorization violation without mutating the database."""

    violations: list[str] = []
    missing_roles = sorted(REQUIRED_ROLES.difference(topology.known_roles))
    if missing_roles:
        violations.append("missing required roles: " + ", ".join(missing_roles))

    app_role = "fin_app"
    importer_role = "fin_history_importer"
    auditor_role = "fin_readonly_auditor"
    schema_owner_role = "fin_schema_owner"

    for schema in sorted(FINANCE_SCHEMAS):
        if topology.schema_owners.get(schema) != schema_owner_role:
            violations.append(f"{schema} must be owned by fin_schema_owner")

    if any(owner == app_role for schema, owner in topology.schema_owners.items() if schema in FINANCE_SCHEMAS):
        violations.append("fin_app must not own finance schemas")
    if app_role in topology.bypass_rls_roles:
        violations.append("fin_app must not have BYPASSRLS")
    if app_role in topology.schema_create_roles:
        violations.append("fin_app must not have CREATE on finance schemas")
    if app_role in topology.database_ddl_roles:
        violations.append("fin_app must not have database-level DDL capabilities")
    for restricted_role in (importer_role, auditor_role):
        if restricted_role in topology.database_ddl_roles:
            violations.append(f"{restricted_role} must not have database-level DDL capabilities")
    for restricted_role in (app_role, importer_role, auditor_role):
        if schema_owner_role in topology.role_memberships.get(restricted_role, set()):
            violations.append(f"{restricted_role} must not be a member of fin_schema_owner")
    if _has_write_privilege(topology, app_role, "fin_history"):
        violations.append("fin_app must not write fin_history")
    if _has_write_privilege(topology, importer_role, "fin_current"):
        violations.append("fin_history_importer must not write fin_current")
    if _has_write_privilege(topology, auditor_role, "fin_current") or _has_write_privilege(
        topology, auditor_role, "fin_history"
    ):
        violations.append("fin_readonly_auditor must not write finance schemas")
    return violations


def inspect_topology(database_url: str) -> FinanceRoleTopology:
    """Collect privilege metadata with read-only catalog queries."""

    from sqlalchemy import create_engine, text

    schema_owners: dict[str, str] = {}
    bypass_rls_roles: set[str] = set()
    schema_create_roles: set[str] = set()
    database_ddl_roles: set[str] = set()
    table_privileges: dict[tuple[str, str], set[str]] = {}
    role_memberships: dict[str, set[str]] = {}
    known_roles: set[str] = set()
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            role_rows = connection.execute(
                text(
                    "select rolname, rolbypassrls, rolcreaterole, rolcreatedb, rolsuper "
                    "from pg_roles where rolname !~ '^pg_'"
                )
            )
            for name, bypass_rls, can_create_role, can_create_database, is_superuser in role_rows:
                known_roles.add(str(name))
                if bypass_rls:
                    bypass_rls_roles.add(str(name))
                if can_create_role or can_create_database or is_superuser:
                    database_ddl_roles.add(str(name))

            owner_rows = connection.execute(
                text(
                    "select nspname, pg_get_userbyid(nspowner) "
                    "from pg_namespace where nspname in ('fin_current', 'fin_history', 'fin_read')"
                )
            )
            for schema, owner in owner_rows:
                schema_owners[str(schema)] = str(owner)

            create_rows = connection.execute(
                text(
                    "select role.rolname, schema.nspname "
                    "from pg_roles role cross join pg_namespace schema "
                    "where schema.nspname in ('fin_current', 'fin_history', 'fin_read') "
                    "and role.rolname !~ '^pg_' "
                    "and has_schema_privilege(role.rolname, schema.nspname, 'CREATE')"
                )
            )
            for role, _schema in create_rows:
                schema_create_roles.add(str(role))

            # Do not inspect only direct ACL rows: grants through PUBLIC or a
            # role membership are still effective privileges and must block a
            # least-privilege release.  The catalog query below is read-only
            # and asks PostgreSQL for each role's effective table privileges.
            grant_rows = connection.execute(
                text(
                    "select role.rolname, schema.nspname, privilege.privilege_type "
                    "from pg_roles role "
                    "cross join pg_namespace schema "
                    "cross join lateral unnest(array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) "
                    "as privilege(privilege_type) "
                    "where schema.nspname in ('fin_current', 'fin_history', 'fin_read') "
                    "and role.rolname !~ '^pg_' "
                    "and exists (select 1 from pg_class relation "
                    "            where relation.relnamespace=schema.oid "
                    "              and relation.relkind in ('r','p','v','m','f') "
                    "              and has_table_privilege(role.oid, relation.oid, privilege.privilege_type))"
                )
            )
            for grantee, schema, privilege in grant_rows:
                table_privileges.setdefault((str(grantee), str(schema)), set()).add(str(privilege).upper())

            membership_rows = connection.execute(
                text(
                    "select member.rolname, owner.rolname "
                    "from pg_roles member cross join pg_roles owner "
                    "where member.rolname in ('fin_app','fin_history_importer','fin_readonly_auditor') "
                    "and owner.rolname='fin_schema_owner' "
                    "and pg_has_role(member.oid, owner.oid, 'MEMBER')"
                )
            )
            for member, parent in membership_rows:
                role_memberships.setdefault(str(member), set()).add(str(parent))
    finally:
        engine.dispose()

    return FinanceRoleTopology(
        known_roles=known_roles,
        schema_owners=schema_owners,
        bypass_rls_roles=bypass_rls_roles,
        schema_create_roles=schema_create_roles,
        database_ddl_roles=database_ddl_roles,
        table_privileges=table_privileges,
        role_memberships=role_memberships,
    )


def main() -> int:
    from app.core.config import settings

    topology = inspect_topology(settings.DATABASE_URL_SYNC)
    violations = validate_role_separation(topology)
    print(json.dumps({"status": "ready" if not violations else "no_go", "violations": violations}, ensure_ascii=False))
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
