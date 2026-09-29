from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_testcontainers_is_not_a_dependency():
    for name in ("pyproject.toml", "uv.lock"):
        assert "testcontainers" not in (ROOT / name).read_text().lower()
