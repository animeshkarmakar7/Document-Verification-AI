from logging.config import fileConfig

from alembic import context
from app.config.settings import settings
from app.database.base import Base

# Import models so SQLAlchemy metadata knows about them
from app.models.clause import Clause  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.ocr_result import OCRResult  # noqa: F401
from sqlalchemy import engine_from_config, pool

config = context.config


if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def get_database_url() -> str:
    return (
        f"postgresql+psycopg2://"
        f"{settings.DATABASE_USER}:"
        f"{settings.DATABASE_PASSWORD}@"
        f"{settings.DATABASE_HOST}:"
        f"{settings.DATABASE_PORT}/"
        f"{settings.DATABASE_NAME}"
    )


def run_migrations_offline() -> None:

    url = get_database_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
        },
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:

    configuration = config.get_section(
        config.config_ini_section,
        {}
    )

    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():

    run_migrations_offline()

else:

    run_migrations_online()
