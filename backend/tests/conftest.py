import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, event

from app.ai.client import FakeAIClient
from app.database import Base, get_db
from app.deps import get_ai
from app.main import create_app

RESUME = (
    "Jane Doe — Software Engineer. 4 years building web apps with Python, FastAPI, React and "
    "PostgreSQL. Deployed services on AWS with Docker. Led a team of 3 engineers."
)
JD = (
    "Acme Corp is hiring a Backend Engineer. Requirements: Python, FastAPI, PostgreSQL, Docker, "
    "Kubernetes and AWS. Experience with Kafka is a plus."
)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys = ON")

    from app import models  # noqa: F401
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_ai] = FakeAIClient
    with TestClient(app) as c:
        c.session_factory = Session
        yield c


def signup(client, email="jane@example.com", name="Jane"):
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return signup(client)
