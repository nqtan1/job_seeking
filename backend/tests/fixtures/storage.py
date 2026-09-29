"""Placeholder in-memory storage. Replaced by the real ``Storage`` protocol fake in P1-09."""

import pytest


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()
