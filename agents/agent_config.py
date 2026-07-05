from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Literal, Optional
import json
import os

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

Provider = Literal["vertex", "api_key"]


def _get_gemini_api_key_from_env() -> Optional[str]:
    """Get Gemini API key from environment, checking both primary and fallback vars."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _get_vertex_project_id_from_env() -> Optional[str]:
    """Get Vertex AI project ID from environment."""
    return os.getenv("GOOGLE_CLOUD_PROJECT")


def _get_vertex_location_from_env() -> Optional[str]:
    """Get Vertex AI location from environment."""
    return os.getenv("GOOGLE_CLOUD_LOCATION")


def _get_application_credentials_path_from_env() -> Optional[str]:
    """Get Google application credentials path from environment."""
    value = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    return str(Path(value).expanduser()) if value else None


@dataclass(slots=True)
class AgentConfig:
    """
    Configuration class for agents.
    Loads settings from JSON/YAML config file with env var fallbacks.
    Supports both API key and Vertex AI authentication modes.
    """
    provider: Provider = "vertex"
    model_name: str = "gemini-2.5-flash-lite"
    temperature: float = 0.7
    max_history: int = 50

    project_id: Optional[str] = None
    location: Optional[str] = None
    api_key: Optional[str] = None
    credentials_path: Optional[str] = None

    optional_params: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        config_path: Optional[str | Path] = None,
        provider: Optional[Provider] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_history: Optional[int] = None,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        credentials_path: Optional[str] = None,
        optional_params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ):
        """
        Initialize agent configuration.

        Load from config file first, then override with explicit params, then apply env fallbacks.

        Args:
            config_path: Path to JSON or YAML config file (optional).
            provider: Backend provider ("vertex" or "api_key").
            model_name: Gemini model name.
            temperature: Model temperature (0.0 to 2.0).
            max_history: Max conversation history messages.
            api_key: Gemini API key (API key mode).
            project_id: GCP project ID (Vertex mode).
            location: GCP region (Vertex mode).
            credentials_path: Path to credentials JSON (Vertex mode).
            optional_params: Additional model params.
            **kwargs: Extra optional params.
        """
        file_data = self._load_config_file(config_path) if config_path else {}

        self.provider = provider if provider is not None else file_data.get("provider", "vertex")
        self.model_name = (
            model_name if model_name is not None else file_data.get("model_name", "gemini-2.5-flash-lite")
        )
        self.temperature = self._validate_temperature(
            temperature if temperature is not None else file_data.get("temperature", 0.7)
        )
        self.max_history = (
            max_history if max_history is not None else file_data.get("max_history", 50)
        )

        self.project_id = (
            project_id
            if project_id is not None
            else file_data.get("project_id")
        )
        self.location = (
            location if location is not None else file_data.get("location")
        )
        self.api_key = (
            api_key if api_key is not None else file_data.get("api_key")
        )
        self.credentials_path = (
            credentials_path
            if credentials_path is not None
            else file_data.get("credentials_path")
        )

        file_optional_params = file_data.get("optional_params", {})
        self.optional_params = {
            **file_optional_params,
            **(optional_params or {}),
            **kwargs,
        }

        self._apply_env_fallbacks()
        self._validate()

    @staticmethod
    def _load_config_file(config_path: str | Path) -> Dict[str, Any]:
        """Load configuration from JSON or YAML file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        suffix = path.suffix.lower()
        with open(path, "r", encoding="utf-8") as file:
            if suffix == ".json":
                raw_data = json.load(file)

            elif suffix in {".yaml", ".yml"}:
                if not HAS_YAML:
                    raise ImportError(
                        "PyYAML is required to load YAML config files. "
                        "Install with: pip install pyyaml"
                    )
                raw_data = yaml.safe_load(file) or {}

            else:
                raise ValueError(f"Config file must be .json, .yaml, or .yml, got {suffix}")

        if isinstance(raw_data, dict) and isinstance(raw_data.get("llm"), dict):
            merged_data = {**raw_data, **raw_data["llm"]}
            merged_data.pop("llm", None)
            return merged_data

        return raw_data

    def _apply_env_fallbacks(self) -> None:
        """Apply environment variable fallbacks for missing config values."""
        if self.provider == "api_key":
            self.api_key = self.api_key or _get_gemini_api_key_from_env()
        elif self.provider == "vertex":
            self.project_id = self.project_id or _get_vertex_project_id_from_env()
            self.location = self.location or _get_vertex_location_from_env()
            self.credentials_path = (
                self.credentials_path or _get_application_credentials_path_from_env()
            )

        if self.credentials_path:
            self.credentials_path = str(Path(self.credentials_path).expanduser())
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path

    def _validate(self) -> None:
        """Validate that required values are present for chosen provider."""
        if self.provider not in ("vertex", "api_key"):
            raise ValueError("provider must be either 'vertex' or 'api_key'")

        if self.provider == "api_key" and not self.api_key:
            raise ValueError(
                "API key mode requires GEMINI_API_KEY or GOOGLE_API_KEY env var"
            )

        if self.provider == "vertex":
            if not self.project_id:
                raise ValueError(
                    "Vertex mode requires GOOGLE_CLOUD_PROJECT env var"
                )
            if not self.location:
                raise ValueError(
                    "Vertex mode requires GOOGLE_CLOUD_LOCATION env var"
                )

    @staticmethod
    def _validate_temperature(temp: float) -> float:
        """Validate and clamp temperature to valid range (0.0 to 2.0)."""
        if temp < 0.0:
            return 0.0
        if temp > 2.0:
            return 2.0
        return temp

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary (excludes sensitive api_key)."""
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_history": self.max_history,
            "project_id": self.project_id,
            "location": self.location,
            "credentials_path": self.credentials_path,
            "optional_params": self.optional_params,
        }

    def __repr__(self) -> str:
        """String representation of config."""
        return (
            f"AgentConfig(provider={self.provider!r}, model_name={self.model_name!r}, "
            f"temperature={self.temperature}, max_history={self.max_history}, "
            f"project_id={self.project_id!r}, location={self.location!r})"
        )