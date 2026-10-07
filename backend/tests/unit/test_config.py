import pytest
from pydantic import ValidationError

from recruitai.config import AGENTS, Settings

DB = "postgresql+psycopg://u:p@localhost:5432/x_test"

# Every prod-only guard test starts from a baseline that satisfies every *other* prod guard,
# then flips exactly the one setting under test. Keeps new guards from silently breaking
# older tests the way individually-patched env vars did.
PROD_OK = {
    "ENV": "prod",
    "DATABASE_URL": DB,
    "FIREBASE_PROJECT_ID": "prod-project",
    "STORAGE_BACKEND": "gcs",
}


def _set(monkeypatch, overrides: dict[str, str | None] | None = None) -> None:
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)  # set by conftest
    for key, value in {**PROD_OK, **(overrides or {})}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_missing_required_settings_fail_fast(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("DATABASE_URL", DB)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("ENV", "local")
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_baseline_is_valid(monkeypatch):
    """Sanity check for the fixture above: if this fails, every guard test below is
    meaningless (it would "pass" only because the baseline itself never validates)."""
    _set(monkeypatch)
    Settings(_env_file=None)


def test_prod_refuses_the_firebase_emulator(monkeypatch):
    _set(monkeypatch, {"FIREBASE_AUTH_EMULATOR_HOST": "localhost:9099"})
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_refuses_local_storage(monkeypatch):
    _set(monkeypatch, {"STORAGE_BACKEND": None})  # defaults to "local"
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_refuses_a_qwen_agent(monkeypatch):
    _set(monkeypatch)
    agents = {a: {"provider": "gemini"} for a in AGENTS} | {
        "coach": {"provider": "qwen"}
    }
    with pytest.raises(ValidationError):
        Settings(_env_file=None, agents=agents)


def test_every_agent_must_be_routed(monkeypatch):
    _set(monkeypatch, {"ENV": "local", "STORAGE_BACKEND": "local"})
    monkeypatch.setenv(
        "CONFIG_FILE", ""
    )  # init values are deep-merged with the test yaml
    with pytest.raises(ValidationError, match="missing"):
        Settings(_env_file=None, agents={"fit": {"provider": "qwen"}})


def test_gemini_auth_is_detected_from_env(monkeypatch):
    _set(monkeypatch, {"ENV": "local", "STORAGE_BACKEND": "local"})
    assert Settings(_env_file=None).gemini_auth == "vertex"  # no key
    assert Settings(_env_file=None, gemini_api_key="k").gemini_auth == "api_key"
    both = Settings(_env_file=None, gemini_api_key="k", google_genai_use_vertexai=True)
    assert both.gemini_auth == "vertex"
    _set(monkeypatch)  # prod ignores a key
    assert Settings(_env_file=None, gemini_api_key="k").gemini_auth == "vertex"


def test_prod_cannot_disable_app_check(monkeypatch):
    _set(monkeypatch, {"APP_CHECK_ENFORCED": "false"})
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_qwen_vl_key_accepts_the_short_env_name(monkeypatch):
    _set(monkeypatch, {"ENV": "local", "QWEN_VL_KEY": "k"})
    assert Settings(_env_file=None).qwen_vl_api_key == "k"  # type: ignore[call-arg]


def test_config_yaml_is_overridden_by_env(monkeypatch, tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(
        "ai_daily_quota_per_user: 7\nagents:\n"
        + "".join(f"  {a}: {{provider: qwen, model: m}}\n" for a in AGENTS)
    )
    _set(monkeypatch, {"ENV": "local", "STORAGE_BACKEND": "local"})
    monkeypatch.setenv("CONFIG_FILE", str(f))
    s = Settings(_env_file=None)
    assert (s.provider_for("fit@1"), s.ai_daily_quota_per_user) == ("qwen", 7)
    monkeypatch.setenv("AI_DAILY_QUOTA_PER_USER", "9")
    assert Settings(_env_file=None).ai_daily_quota_per_user == 9


def test_agent_model_override(monkeypatch):
    _set(monkeypatch, {"ENV": "local", "STORAGE_BACKEND": "local"})
    agents = {a: {"provider": "gemini"} for a in AGENTS} | {
        "fit": {"provider": "qwen", "model": "big"}
    }
    s = Settings(_env_file=None, agents=agents)
    assert (s.provider_for("fit@1"), s.agent_model("fit@1", "dflt")) == ("qwen", "big")
    assert (s.provider_for("coach@1"), s.agent_model("coach@1", "dflt")) == (
        "gemini",
        "dflt",
    )
