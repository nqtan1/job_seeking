from typing import Optional
import os


class AgentConfig:
    """
    Configuration class for agents
    Handles model settings, API keys, and optional parameters
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        model_name: str = "gemini-2.5-flash-lite",
        max_history: int = 50,
        **kwargs
    ):
        """
        Initialize agent configuration
        
        Args:
            name: Agent name for identification
            api_key: Google Gemini API key (defaults to GEMINI_API_KEY env var)
            temperature: Model temperature (0.0 to 2.0), controls randomness
                - 0.0: Deterministic, focused responses
                - 0.7: Balanced (default)
                - 2.0: Maximum creativity
            model_name: Gemini model to use
            max_history: Maximum conversation history messages to keep
            **kwargs: Additional optional parameters
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.temperature = self._validate_temperature(temperature)
        self.model_name = model_name
        self.max_history = max_history
        
        # Store optional parameters
        self.optional_params = kwargs
    
    
    def _validate_temperature(self, temp: float) -> float:
        """
        Validate and clamp temperature to valid range (0.0 to 2.0)
        
        Args:
            temp: Temperature value
            
        Returns:
            float: Validated temperature value
        """
        if temp < 0.0:
            return 0.0
        elif temp > 2.0:
            return 2.0
        return temp
    
    
    def to_dict(self) -> dict:
        """
        Convert config to dictionary (excludes sensitive api_key)
        
        Returns:
            dict: Configuration as dictionary
        """
        return {
            "temperature": self.temperature,
            "model_name": self.model_name,
            "max_history": self.max_history,
            "optional_params": self.optional_params
        }
    
    
    def __repr__(self) -> str:
        """String representation of config"""
        return f"AgentConfig(name={self.name}, model={self.model_name}, temp={self.temperature})"