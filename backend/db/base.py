"""SQLAlchemy declarative base.

Models live in the ``models`` package and register themselves on ``Base.metadata``
when imported; import ``models`` (as Alembic's env.py does) to load them all.
Keeping this module free of model imports avoids a circular import.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


__all__ = ["Base"]
