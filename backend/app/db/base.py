from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared declarative base for all SQLAlchemy models.
    Import this in every model module so Alembic can detect them.
    """
    pass
