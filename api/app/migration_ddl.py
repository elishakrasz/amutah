"""Trigger DDL shared by migrations from 0003 on.

Migrations pass their own frozen table and column lists, so the output for a
given migration never changes when models do. Do not change what these
functions emit; add a new function instead.

SQLite note: Alembic batch mode rebuilds a table (create new, copy, drop old)
for most ALTERs, and the rebuild drops that table's triggers. Any migration
that batch-alters a guarded table must call sqlite_recreate_guards() last.
"""

from collections.abc import Callable, Iterable

Exec = Callable[[str], object]


def sqlite_append_only(execute: Exec, tables: Iterable[str]) -> None:
    for t in tables:
        execute(f"DROP TRIGGER IF EXISTS {t}_no_update")
        execute(f"DROP TRIGGER IF EXISTS {t}_no_delete")
        execute(
            f"CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t} "
            f"BEGIN SELECT RAISE(ABORT, 'append-only table: {t}'); END"
        )
        execute(
            f"CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} "
            f"BEGIN SELECT RAISE(ABORT, 'append-only table: {t}'); END"
        )


def sqlite_case_guard(
    execute: Exec, immutable: Iterable[str], nullable_only: Iterable[str]
) -> None:
    changed = [f"NEW.{c} IS NOT OLD.{c}" for c in immutable] + [
        f"(NEW.{c} IS NOT OLD.{c} AND NEW.{c} IS NOT NULL)" for c in nullable_only
    ]
    execute("DROP TRIGGER IF EXISTS aid_case_guard_update")
    execute("DROP TRIGGER IF EXISTS aid_case_no_delete")
    execute(
        "CREATE TRIGGER aid_case_guard_update BEFORE UPDATE ON aid_case "
        f"WHEN {' OR '.join(changed)} "
        "BEGIN SELECT RAISE(ABORT, 'aid_case: only workflow columns may change'); END"
    )
    execute(
        "CREATE TRIGGER aid_case_no_delete BEFORE DELETE ON aid_case "
        "BEGIN SELECT RAISE(ABORT, 'aid_case rows are never deleted'); END"
    )


def pg_append_only(execute: Exec, tables: Iterable[str]) -> None:
    """Requires forbid_mutation() from migration 0002."""
    for t in tables:
        execute(f"DROP TRIGGER IF EXISTS {t}_no_mutation ON {t}")
        execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
        execute(
            f"CREATE TRIGGER {t}_no_mutation BEFORE UPDATE OR DELETE ON {t} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
        )
        execute(
            f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} "
            "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
        )


def pg_drop_append_only(execute: Exec, tables: Iterable[str]) -> None:
    for t in tables:
        execute(f"DROP TRIGGER IF EXISTS {t}_no_mutation ON {t}")
        execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")


def pg_case_guard(execute: Exec, immutable: Iterable[str], nullable_only: Iterable[str]) -> None:
    """Replaces the function body; the trigger from 0002 keeps calling it."""
    changed = [f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in immutable] + [
        f"(NEW.{c} IS DISTINCT FROM OLD.{c} AND NEW.{c} IS NOT NULL)" for c in nullable_only
    ]
    execute(
        f"""
        CREATE OR REPLACE FUNCTION aid_case_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'aid_case rows are never deleted'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            IF {" OR ".join(changed)} THEN
                RAISE EXCEPTION 'aid_case: only workflow columns may change'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END $$
        """
    )


def enum_check_sql(column: str, values: Iterable[str]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"
