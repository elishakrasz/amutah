import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# Settings are read from the environment; set test values before app imports.
os.environ.update(
    {
        "AMUTAH_ENVIRONMENT": "test",
        "AMUTAH_NATIONAL_ID_HMAC_KEY": "test-hmac-key-" * 3,
        "AMUTAH_FIELD_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "AMUTAH_SIGNING_KEY": "test-signing-key-" * 3,
    }
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import Engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import make_engine  # noqa: E402

API_ROOT = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("AMUTAH_TEST_PG_URL")


def alembic_config(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


def _dialect_params() -> list[str]:
    return ["sqlite", "postgresql"] if PG_URL else ["sqlite"]


@pytest.fixture(params=_dialect_params())
def db_url(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[str]:
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'test.db'}"
        return
    assert PG_URL is not None
    schema = f"t_{uuid.uuid4().hex[:12]}"
    admin = make_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    sep = "&" if "?" in PG_URL else "?"
    yield f"{PG_URL}{sep}options=-csearch_path%3D{schema}"
    with admin.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin.dispose()


@pytest.fixture
def migrated_engine(db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(db_url), "head")
    engine = make_engine(db_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrated_engine: Engine) -> Iterator[Session]:
    with Session(migrated_engine, expire_on_commit=False) as s:
        yield s
