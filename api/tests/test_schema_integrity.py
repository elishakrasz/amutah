"""Guards against the two ways a migration can silently weaken the schema:
an enum or model CHECK that never reaches the database, and SQLite batch
rebuilds that drop a table's triggers."""

from alembic import command
from sqlalchemy import CheckConstraint, Engine, Enum, inspect

from app.models import Base, append_only_tables
from tests.conftest import alembic_config
from tests.test_append_only import _trigger_tables


def _db_checks(engine: Engine) -> dict[str, list[str]]:
    insp = inspect(engine)
    return {
        t: [str(c["sqltext"]) for c in insp.get_check_constraints(t)] for t in Base.metadata.tables
    }


def test_every_enum_column_is_checked_in_the_database(migrated_engine: Engine) -> None:
    checks = _db_checks(migrated_engine)
    missing = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if isinstance(col.type, Enum):
                values = col.type.enums
                if not any(all(f"'{v}'" in sql for v in values) for sql in checks[table.name]):
                    missing.append(f"{table.name}.{col.name}")
    assert missing == []


def test_every_model_check_constraint_is_in_the_database(migrated_engine: Engine) -> None:
    insp = inspect(migrated_engine)
    missing = []
    for table in Base.metadata.sorted_tables:
        db_names = {c["name"] for c in insp.get_check_constraints(table.name)}
        for c in table.constraints:
            if isinstance(c, CheckConstraint) and c.name not in db_names:
                missing.append(str(c.name))
    assert missing == []


def test_triggers_survive_downgrade_and_upgrade(db_url: str) -> None:
    from app.db import make_engine

    cfg = alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")
    engine = make_engine(db_url)
    try:
        assert set(append_only_tables()) | {"aid_case"} <= _trigger_tables(engine)
    finally:
        engine.dispose()
