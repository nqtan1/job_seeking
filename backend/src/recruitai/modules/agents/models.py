"""Imports every agents sub-package's models so ``Base.metadata`` is complete
(``recruitai.models`` imports this module)."""

from recruitai.modules.agents.connections import models as _connections
from recruitai.modules.agents.contacts import models as _contacts
from recruitai.modules.agents.flows import models as _flows
from recruitai.modules.agents.helpers import models as _helpers

__all__ = ["_connections", "_contacts", "_flows", "_helpers"]
