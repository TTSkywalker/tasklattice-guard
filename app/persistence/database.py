from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeAlias

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base

DatabaseLocator: TypeAlias = str | Path


class Database:
    """Own the SQLAlchemy engine and short-lived unit-of-work sessions."""

    def __init__(self, locator: DatabaseLocator) -> None:
        self.url = database_url(locator)
        parsed_url = make_url(self.url)
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if parsed_url.get_backend_name() == "sqlite":
            database = parsed_url.database
            if database and database != ":memory:":
                Path(database).expanduser().resolve().parent.mkdir(
                    parents=True, exist_ok=True
                )
            engine_options["connect_args"] = {"check_same_thread": False}
            if database in {None, "", ":memory:"}:
                engine_options["poolclass"] = StaticPool
        self.engine: Engine = create_engine(self.url, **engine_options)
        if parsed_url.get_backend_name() == "sqlite":
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self._sessions = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._sessions()
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self._sessions.begin() as session:
            yield session

    def create_schema(self) -> None:
        """Create the current ORM schema for a new deployment."""
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()


def database_url(locator: DatabaseLocator) -> str:
    if isinstance(locator, Path):
        return f"sqlite:///{locator.expanduser().resolve()}"
    value = locator.strip()
    if "://" in value:
        return value
    return f"sqlite:///{Path(value).expanduser().resolve()}"


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    # SQLAlchemy has no portable switch for SQLite's connection-local FK flag.
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
