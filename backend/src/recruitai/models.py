"""Imports every module's models so ``Base.metadata`` is complete (Alembic autogenerate,
``alembic check`` and tests). Add a line here whenever a module gets models."""

from recruitai.ai import usage as _usage
from recruitai.modules.documents import models as _documents
from recruitai.modules.identity import models as _identity

__all__ = ["_documents", "_identity", "_usage"]
