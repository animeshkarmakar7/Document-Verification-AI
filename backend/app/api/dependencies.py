from collections.abc import Generator

from app.database.database import SessionLocal
from sqlalchemy.orm import Session


def get_db() -> Generator[Session]:

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()