"""
数据库配置与会话管理。
生产使用 PostgreSQL（DATABASE_URL）；未设置时使用 SQLite（仅开发）。
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from pathlib import Path

from app.config import settings

if settings.database_url:
    SQLALCHEMY_DATABASE_URL = settings.database_url
    connect_args = {}
    DATABASE_PATH = ""
else:
    _db_path = Path("./data/users.db")
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{_db_path}"
    connect_args = {"check_same_thread": False}
    DATABASE_PATH = str(_db_path)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """启动时创建表（若使用 PostgreSQL，需先执行 docs/postgresql_schema.sql）。"""
    from app.db.models import User
    from app.db.activity_models import UserActivityLog, LoginAttempt
    from app.db.refresh_token_models import RefreshToken
    from app.db.password_reset_models import PasswordResetToken
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """仅开发/测试用：删除所有表。"""
    Base.metadata.drop_all(bind=engine)
