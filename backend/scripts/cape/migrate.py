import pathlib

from cape.db import get_pg_conn


def main() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    migrations_dir = repo_root / "backend" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        raise RuntimeError(f"No migration files found in {migrations_dir}")

    with get_pg_conn() as conn, conn.cursor() as cur:
        for migration_path in migration_files:
            sql = migration_path.read_text(encoding="utf-8")
            cur.execute(sql)
        conn.commit()

    print(f"Applied {len(migration_files)} CAPE migrations")


if __name__ == "__main__":
    main()
