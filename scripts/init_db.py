"""
Initialize database by creating all tables.
Run this script once before starting the application.
"""
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, DATABASE_PATH


def main():
    """Initialize database."""
    print("=" * 60)
    print("Database Initialization")
    print("=" * 60)
    print(f"Database: {DATABASE_PATH or 'PostgreSQL (DATABASE_URL)'}")
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
