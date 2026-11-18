"""Every tool pack, imported once so its tools register in ``core.tools`` (ADR 0039).
The API (main.py) and the worker (worker.py) import this module; a new pack is one line here."""

from recruitai.modules.agents.blocks import catalogue  # noqa: F401  web, messages, core
from recruitai.modules.agents.flows import chat_tools as _flows  # noqa: F401  agents
from recruitai.modules.applications import tools as _applications  # noqa: F401  career
from recruitai.modules.candidates import tools as _candidates  # noqa: F401  career
from recruitai.modules.coach import inbox as _inbox  # noqa: F401  the core.inbox sink
from recruitai.modules.cvreview import tools as _cvreview  # noqa: F401  career
from recruitai.modules.jobs import tools as _jobs  # noqa: F401  career
from recruitai.modules.letters import tools as _letters  # noqa: F401  career
from recruitai.modules.matching import tools as _matching  # noqa: F401  career
from recruitai.modules.notes import tools as _notes  # noqa: F401  web (notes)
