"""
Initialize database by creating all tables.
Run this script once before starting the application.
PostgreSQL: 若 DATABASE_URL 指向的数据库不存在，会先自动创建再建表。
"""
import re
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.db.database import init_db, DATABASE_PATH


def ensure_postgres_database_exists() -> None:
    """若使用 PostgreSQL 且目标数据库不存在，则先创建数据库。"""
    if not settings.database_url:
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(settings.database_url)
    dbname = url.database
    if not dbname or not re.match(r"^[a-zA-Z0-9_]+$", dbname):
        raise ValueError(f"Invalid or missing database name in DATABASE_URL: {dbname!r}")

    # 连到默认库 postgres，用于执行 CREATE DATABASE
    admin_url = url.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        r = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname})
        if r.scalar() is None:
            conn.execute(text(f'CREATE DATABASE "{dbname}"'))
            print(f"[OK] PostgreSQL database '{dbname}' created.")
        else:
            print(f"[OK] PostgreSQL database '{dbname}' already exists.")
    engine.dispose()


def main():
    """Initialize database."""
    print("=" * 60)
    print("Database Initialization")
    print("=" * 60)
    print(f"Database: {DATABASE_PATH or 'PostgreSQL (DATABASE_URL)'}")
    print()

    # PostgreSQL: 确保目标数据库存在
    if settings.database_url:
        ensure_postgres_database_exists()
        print()

    # SQLite: 若文件已存在可提示是否覆盖
    db_path = Path(DATABASE_PATH) if DATABASE_PATH else None
    if db_path and db_path.exists():
        print("[WARNING] Database file already exists!")
        response = input("Do you want to recreate it? (y/N): ")
        if response.lower() != 'y':
            print("[CANCELLED] Initialization cancelled.")
            return

        # Backup existing database
        backup_path = db_path.with_suffix('.db.backup')
        import shutil
        shutil.copy(db_path, backup_path)
        print(f"[OK] Existing database backed up to: {backup_path}")

    # Initialize database
    init_db()
    print()
    print("=" * 60)
    print("[SUCCESS] Database initialization complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Create an admin user: python scripts/create_admin.py")
    print("2. Start the application: uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
