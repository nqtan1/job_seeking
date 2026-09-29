import uuid

from recruitai.core.ids import new_id


def test_new_id_is_a_stdlib_uuid_version_7():
    value = new_id()

    assert isinstance(value, uuid.UUID)
    assert value.version == 7


def test_new_ids_are_unique_and_time_ordered():
    ids = [new_id() for _ in range(2000)]

    assert len(set(ids)) == len(ids)
    assert [i.int >> 80 for i in ids] == sorted(
        i.int >> 80 for i in ids
    )  # 48-bit ms timestamp
