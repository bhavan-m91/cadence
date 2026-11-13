"""Test harness: real PostgreSQL, migrations applied once, each test in a transaction that is rolled back."""

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("EMAIL_BACKEND", "memory")
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_session  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services import email_service  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _migrated_database():
    url = get_settings().test_database_url
    env = {**os.environ, "DATABASE_URL": url}

    async def reset():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    import asyncio

    asyncio.run(reset())
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return url


@pytest_asyncio.fixture(scope="session")
async def engine(_migrated_database):
    eng = create_async_engine(_migrated_database)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        yield session
        await session.close()
        await trans.rollback()


@pytest.fixture(autouse=True)
def _reset_state():
    limiter.reset()
    email_service.OUTBOX.clear()
    yield


@pytest_asyncio.fixture
async def client(db):
    app = create_app()

    async def override_session():
        yield db

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
