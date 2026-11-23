import os

from alembic import context
from sqlalchemy import create_engine

from app.models import Base

url = os.environ.get("DATABASE_URL", "sqlite:///./properm.db")
target_metadata = Base.metadata


def run() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()
