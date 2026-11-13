import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

USER = {"username": "john", "email": "john@example.com", "password": "pass1234"}


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_register_success(client):
    res = client.post("/auth/register", json=USER)
    assert res.status_code == 201
    assert res.json()["username"] == "john"
    assert "password" not in res.json()


def test_register_duplicate(client):
    client.post("/auth/register", json=USER)
    res = client.post("/auth/register", json=USER)
    assert res.status_code == 400


def test_login_success(client):
    client.post("/auth/register", json=USER)
    res = client.post("/auth/login", json={"username": "john", "password": "pass1234"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client):
    client.post("/auth/register", json=USER)
    res = client.post("/auth/login", json={"username": "john", "password": "wrong"})
    assert res.status_code == 401


def test_vision_requires_token(client):
    res = client.post("/vision/describe", data={"text": "hi"})
    assert res.status_code in (401, 403)