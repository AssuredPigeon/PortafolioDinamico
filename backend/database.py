from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_database_url
from backend.models import Base


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_database_url()
    connect_args: dict[str, Any] = {}
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 20

    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=20000")
            cursor.close()

    return engine


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(target_engine: Engine | None = None) -> None:
    """Crea las tablas Usuario, Repositorio y ActividadCommit si no existen y migra columnas nuevas."""
    active_engine = target_engine or engine
    Base.metadata.create_all(bind=active_engine)

    inspector = inspect(active_engine)
    if inspector.has_table("repositorio"):
        existing_cols = {col["name"] for col in inspector.get_columns("repositorio")}
        if "detalle_tecnico" not in existing_cols:
            col_sql = (
                "JSONB NOT NULL DEFAULT '{}'::jsonb"
                if active_engine.dialect.name == "postgresql"
                else "JSON NOT NULL DEFAULT '{}'"
            )
            with active_engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE repositorio ADD COLUMN detalle_tecnico {col_sql}"))

def get_db_dialect_name(target_engine: Engine | None = None) -> str:
    active = target_engine or engine
    return active.dialect.name


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

