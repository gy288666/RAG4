"""SQLAlchemy 引擎与会话管理。

同时兼容 MySQL 8（生产）与 SQLite（本地开发 / 自动化测试）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""


def _build_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {"echo": settings.DB_ECHO, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # MySQL：开启连接预检与回收，避免 8 小时空闲断连
        kwargs.update(pool_pre_ping=True, pool_recycle=3600, pool_size=10, max_overflow=20)
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖注入用的数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """后台线程 / 脚本中使用的事务性会话上下文。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """建表（仅在表不存在时创建）。

    生产环境请以 ``docs/init_db.sql`` 为准，本函数主要服务于开发与测试。
    """
    from app import models  # noqa: F401  确保所有模型完成注册

    Base.metadata.create_all(bind=engine)
