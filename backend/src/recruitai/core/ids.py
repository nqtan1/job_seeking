"""Primary-key generation. UUIDv7 is time-sortable (good index locality); neither Postgres 16
nor Python 3.13 generates it, so we use ``uuid-utils`` and hand SQLAlchemy a stdlib ``UUID``."""

import uuid

import uuid_utils


def new_id() -> uuid.UUID:
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)
