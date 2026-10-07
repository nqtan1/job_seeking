"""Imports every module's models so ``Base.metadata`` is complete (Alembic autogenerate,
``alembic check`` and tests). Add a line here whenever a module gets models."""

from recruitai.ai import overrides as _overrides
from recruitai.ai import usage as _usage
from recruitai.core import tasks as _tasks
from recruitai.modules.applications import models as _applications
from recruitai.modules.candidates import models as _candidates
from recruitai.modules.coach import models as _coach
from recruitai.modules.documents import models as _documents
from recruitai.modules.identity import models as _identity
from recruitai.modules.jobs import models as _jobs
from recruitai.modules.letters import models as _letters
from recruitai.modules.matching import models as _matching
from recruitai.modules.radar import models as _radar

__all__ = [
    "_applications",
    "_candidates",
    "_coach",
    "_documents",
    "_identity",
    "_jobs",
    "_letters",
    "_matching",
    "_overrides",
    "_radar",
    "_tasks",
    "_usage",
]
