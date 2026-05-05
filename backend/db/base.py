"""SQLAlchemy declarative base and model registry for Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


# Import all models so Alembic / metadata.create_all can discover tables.
from models.conversation import Conversation, Message  # noqa: E402
from models.document import Document  # noqa: E402
from models.user import User  # noqa: E402

__all__ = ["Base", "User", "Conversation", "Message", "Document"]
