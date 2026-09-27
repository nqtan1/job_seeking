import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


def run_migrations(db_path: str) -> None:
    """
    Executes any pending SQL migration scripts on the specified SQLite database.
    """
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Running database migrations on: {db_file.resolve()}")

    with sqlite3.connect(db_file) as conn:
        # Create migrations table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        conn.commit()

        # Locate migrations directory relative to this file (migrations/versions)
        migrations_dir = Path(__file__).resolve().parent / "versions"
        if not migrations_dir.exists() or not migrations_dir.is_dir():
            print(f"Error: Migrations versions directory not found at {migrations_dir.resolve()}", file=sys.stderr)
            sys.exit(1)

        # Retrieve and sort migration files (e.g. 0001_initial_schema.sql)
        migration_files = sorted(migrations_dir.glob("*.sql"))
        if not migration_files:
            print("No migration files found.")
            return

        # Fetch already applied migrations
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations")
        applied_versions = {row[0] for row in cursor.fetchall()}

        for file in migration_files:
            version = file.name
            if version in applied_versions:
                print(f"  [{version}] Already applied.")
                continue

            print(f"  [{version}] Applying migration...")
            try:
                content = file.read_text(encoding="utf-8")
                # Execute full script as a single batch within transaction
                conn.executescript(content)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, datetime.now().isoformat())
                )
                conn.commit()
                print(f"  [{version}] Successfully applied.")
            except Exception as e:
                conn.rollback()
                print(f"Error applying migration {version}: {e}", file=sys.stderr)
                raise e

    print("Database migrations completed successfully.")


def main():
    # Set default database path
    project_root = Path(__file__).resolve().parent.parent
    db_path = os.getenv("BACKGROUND_JOBS_DB_PATH") or str(project_root / "db" / "background_jobs.db")
    
    try:
        run_migrations(db_path)
    except Exception as e:
        print(f"Migrations failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
