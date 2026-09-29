import os

# Must run before anything imports recruitai.main (which builds the app at import time).
# The app under test never gets the dev database: default to the test one.
os.environ.setdefault("ENV", "local")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/recruitai_test",
    ),
)

pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.llm",
    "tests.fixtures.storage",
    "tests.fixtures.auth",
    "tests.fixtures.app",
    "tests.fixtures.queue",
    "tests.fixtures.migrations",
]
