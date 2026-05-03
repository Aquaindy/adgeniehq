import os
from collections.abc import Generator

# Disable rate limiting before app import so the middleware reads the override
# from settings on first instantiation.
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.models import User, Workspace, WorkspaceMember  # noqa: F401  — register tables
from main import app

# Force the cached settings instance to reflect the override (the env var
# applied earlier is read at construction time).
settings.rate_limit_disabled = True


def _resolve_test_db_url() -> str:
    if settings.test_database_url:
        return settings.test_database_url
    # Fall back: append `_test` to the dev DB name.
    if "?" in settings.database_url:
        base, query = settings.database_url.split("?", 1)
        return f"{base}_test?{query}"
    return f"{settings.database_url}_test"


TEST_DATABASE_URL = _resolve_test_db_url()


test_engine = create_engine(TEST_DATABASE_URL, future=True)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)


# Point the production SessionLocal at the test engine so worker tasks
# (which open their own session via `app.db.session.SessionLocal`) read +
# write the test database in sync mode. Without this, tasks pick up a
# session against the dev database and FK constraints blow up.
from app.db import session as _db_session_module  # noqa: E402

_db_session_module.SessionLocal = TestSessionLocal
_db_session_module.engine = test_engine


@pytest.fixture(scope="session", autouse=True)
def _setup_schema() -> Generator[None, None, None]:
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture(autouse=True)
def _truncate_between_tests() -> Generator[None, None, None]:
    yield
    with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _override_get_db() -> Generator[Session, None, None]:
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
