from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.enums import Role
from app.main import create_app
from app.models import AuditEvent
from tests import factories


@pytest.fixture
def client(migrated_engine: Engine) -> Iterator[TestClient]:
    app = create_app()

    def _session() -> Iterator[Session]:
        with Session(migrated_engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_whoami_requires_token(client: TestClient) -> None:
    assert client.get("/api/v1/whoami").status_code == 401
    r = client.get("/api/v1/whoami", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_role_picker_login(client: TestClient, migrated_engine: Engine) -> None:
    with Session(migrated_engine) as s:
        u = factories.staff(s, Role.TREASURER)
        s.commit()
        uid = u.id

    staff = client.get("/api/v1/dev/staff").json()
    assert [p["roles"] for p in staff] == [["treasurer"]]

    r = client.post("/api/v1/dev/login", json={"user_id": str(uid), "role": "treasurer"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "treasurer"

    with Session(migrated_engine) as s:
        events = s.scalars(select(AuditEvent).where(AuditEvent.action == "login")).all()
        assert [(e.actor_id, e.role) for e in events] == [(uid, "treasurer")]


def test_cannot_log_in_with_a_role_not_held(client: TestClient, migrated_engine: Engine) -> None:
    with Session(migrated_engine) as s:
        u = factories.staff(s, Role.TREASURER)
        s.commit()
        uid = u.id
    r = client.post("/api/v1/dev/login", json={"user_id": str(uid), "role": "board_member"})
    assert r.status_code == 403
