"""Create an empty PostgreSQL database for the isolated Kingdee import trial."""

import argparse
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="huabang_ai_kingdee_test")
    args = parser.parse_args()
    connection = psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        dbname="postgres",
    )
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user")
            row = cursor.fetchone()
            if not row or not row[0]:
                raise RuntimeError(f"Database role {settings.DB_USER!r} does not have CREATEDB")
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.database,))
            if cursor.fetchone():
                print(f"Database already exists: {args.database}")
                return
            cursor.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(args.database)))
            print(f"Database created: {args.database}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
