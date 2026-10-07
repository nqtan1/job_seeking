import os
from pathlib import Path

# Must run before anything imports recruitai.main (which builds the app at import time).
# The app under test never gets the dev database: default to the test one.
os.environ.setdefault("ENV", "local")
os.environ.setdefault(  # tests never read backend/config.yaml
    "CONFIG_FILE", str(Path(__file__).parent / "fixtures" / "config.test.yaml")
)
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/recruitai_test",
    ),
)
os.environ["APP_CHECK_ENFORCED"] = "true"  # a dev .env must not weaken the 401 tests
os.environ.setdefault("FIREBASE_PROJECT_ID", "demo-recruitai")
os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")

pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.llm",
    "tests.fixtures.jobs",
    "tests.fixtures.storage",
    "tests.fixtures.auth",
    "tests.fixtures.app",
    "tests.fixtures.real_app",
    "tests.fixtures.queue",
    "tests.fixtures.migrations",
    "tests.fixtures.tasks",
]


import pytest


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Tests reuse the same uids: no test may inherit another's request counts."""
    from recruitai.core import ratelimit

    ratelimit._hits.clear()
