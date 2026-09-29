import uuid
from pathlib import Path

from recruitai.core.ids import new_id

ROOT = Path(__file__).resolve().parents[2]


def test_new_ids_are_unique_time_ordered_uuid7():
    ids = [new_id() for _ in range(2000)]

    assert all(isinstance(i, uuid.UUID) and i.version == 7 for i in ids)
    assert len(set(ids)) == len(ids)
    assert [i.int >> 80 for i in ids] == sorted(
        i.int >> 80 for i in ids
    )  # 48-bit ms timestamp


def test_testcontainers_is_not_a_dependency():
    for name in ("pyproject.toml", "uv.lock"):
        assert "testcontainers" not in (ROOT / name).read_text().lower()
