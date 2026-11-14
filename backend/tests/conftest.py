import gc
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_queueless.db"  # tests must never touch a real database

import pytest  # noqa: E402

import app.models  # noqa: E402,F401  registers tables on Base
from app.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    gc.collect()  # release connections still held by sessions from earlier tests
    engine.dispose()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
