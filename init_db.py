"""
One-shot database initialisation script.

Steps:
  1. Create the PostgreSQL database if it does not exist (skipped if it does).
  2. Run all Alembic migrations to bring the schema up to date (idempotent).

Usage:
    python init_db.py
"""

import asyncio
import subprocess
import sys
from urllib.parse import urlparse

import asyncpg

from app.config import settings


def _parse_db_url(url: str) -> dict:
    clean = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(clean)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
    }


async def create_database_if_missing(params: dict) -> None:
    connect_kwargs = {
        "host": params["host"],
        "port": params["port"],
        "database": "postgres",  # connect to system DB to check/create target
    }
    if params["user"]:
        connect_kwargs["user"] = params["user"]
    if params["password"]:
        connect_kwargs["password"] = params["password"]

    conn = await asyncpg.connect(**connect_kwargs)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", params["database"]
        )
        if exists:
            print(f"  Database '{params['database']}' already exists — retaining existing data.")
        else:
            await conn.execute(f'CREATE DATABASE "{params["database"]}"')
            print(f"  Database '{params['database']}' created.")
    finally:
        await conn.close()


def run_migrations() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Alembic error:\n", result.stderr, file=sys.stderr)
        sys.exit(1)
    print(result.stdout.strip() or "  Migrations up to date.")


async def main() -> None:
    params = _parse_db_url(settings.database_url)

    print("── Step 1: Ensure database exists ──")
    await create_database_if_missing(params)

    print("── Step 2: Run Alembic migrations ──")
    run_migrations()

    print("\nInitialisation complete.")


if __name__ == "__main__":
    asyncio.run(main())
