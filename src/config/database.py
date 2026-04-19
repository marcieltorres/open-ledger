from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import settings

DATABASE_URL = (
    f"postgresql+psycopg://{settings.get_from_env('DATABASE_USER')}:"
    f"{settings.get_from_env('DATABASE_PASS')}@"
    f"{settings.get_from_env('DATABASE_ENDPOINT')}:"
    f"{settings.get_from_env('DATABASE_PORT')}/"
    f"{settings.get_from_env('DATABASE_NAME')}"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
