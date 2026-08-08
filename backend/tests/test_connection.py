import pytest
from app.database.database import engine
from sqlalchemy import text


@pytest.mark.integration
def test_connection():

    with engine.connect() as connection:

        result = connection.execute(
            text("SELECT 1")
        )

        print(result.scalar())


if __name__ == "__main__":
    test_connection()
