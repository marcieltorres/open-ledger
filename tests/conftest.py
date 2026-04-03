import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from src.model.base_model import BaseModel


@pytest.fixture(scope="session")
def postgres_container():
    """Spin up a PostgreSQL container for the test session."""
    with PostgresContainer("postgres:13.3-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def db_engine(postgres_container):
    """Create SQLAlchemy engine connected to test container."""
    url = postgres_container.get_connection_url().replace("psycopg2", "psycopg")
    engine = create_engine(url)
    BaseModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test."""
    session_factory = sessionmaker(bind=db_engine)
    session = session_factory()
    yield session
    session.rollback()
    session.close()


