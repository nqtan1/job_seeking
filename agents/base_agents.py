from abc import ABC
from typing import Optional, Dict, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    BaseMessage,
    ToolMessage,
)

from agents.agent_config import AgentConfig
from utils.logger import get_logger


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        system_prompt: Optional[str] = None,
        logger_name: Optional[str] = None,
        log_file: Optional[str] = None,
        log_level: str = "INFO",
    ):
        self.config = config or AgentConfig()
        self.logger = get_logger(
            name=logger_name or self.__class__.__module__,
            log_file=log_file,
            level=log_level,
        )

        self.logger.debug(
            "Initializing agent with provider=%s model=%s temperature=%s",
            self.config.provider,
            self.config.model_name,
            self.config.temperature,
        )

        self.model = self._create_model()
        self.conversation_history: List[BaseMessage] = []

        if system_prompt:
            self.conversation_history.append(SystemMessage(content=system_prompt))
            self.logger.debug("System prompt added to conversation history")

    def _build_model_kwargs(self) -> Dict:
        model_kwargs = {
            "model": self.config.model_name,
            "temperature": self.config.temperature,
            **self.config.optional_params,
        }

        if self.config.provider == "vertex":
            model_kwargs.update(
                {
                    "vertexai": True,
                    "project": self.config.project_id,
                    "location": self.config.location,
                }
            )
            self.logger.debug(
                "Configured Vertex AI model kwargs for project=%s location=%s",
                self.config.project_id,
                self.config.location,
            )
        else:
            model_kwargs["api_key"] = self.config.api_key
            self.logger.debug("Configured Gemini API-key model kwargs")

        return model_kwargs

    def _create_model(self) -> ChatGoogleGenerativeAI:
        self.logger.debug("Creating model for provider=%s", self.config.provider)
        if self.config.provider == "vertex":
            return self._init_gemini_by_vertex_ai()
        return self._init_gemini_by_api_key()

    def _init_gemini_by_api_key(self) -> ChatGoogleGenerativeAI:
        self.logger.debug("Initializing ChatGoogleGenerativeAI in api_key mode")
        return ChatGoogleGenerativeAI(**self._build_model_kwargs())

    def _init_gemini_by_vertex_ai(self) -> ChatGoogleGenerativeAI:
        self.logger.debug("Initializing ChatGoogleGenerativeAI in vertex mode")
        return ChatGoogleGenerativeAI(**self._build_model_kwargs())

    def chat(self, message: str) -> BaseMessage:
        """Send a new message and get the model response."""
        self.logger.info("chat called")
        self.logger.debug(
            "Incoming message length=%s current_history_size=%s",
            len(message),
            len(self.conversation_history),
        )

        human_msg = HumanMessage(content=message)
        self.conversation_history.append(human_msg)

        response = self.model.invoke(self.conversation_history)
        self.conversation_history.append(response)
        self._truncate_history_smart()

        self.logger.debug(
            "chat completed; history_size=%s",
            len(self.conversation_history),
        )
        return response

    def _truncate_history(self):
        """Keep only the most recent messages."""
        if len(self.conversation_history) > self.config.max_history:
            self.logger.debug(
                "Basic truncation from %s to %s",
                len(self.conversation_history),
                self.config.max_history,
            )
            self.conversation_history = self.conversation_history[-self.config.max_history :]

    def _truncate_history_smart(self):
        """Preserve system messages and trim the oldest conversational messages."""
        if len(self.conversation_history) <= self.config.max_history:
            return

        original_size = len(self.conversation_history)
        system_msgs = [msg for msg in self.conversation_history if isinstance(msg, SystemMessage)]
        conversation_msgs = [msg for msg in self.conversation_history if not isinstance(msg, SystemMessage)]

        space_for_conversation = self.config.max_history - len(system_msgs)
        if space_for_conversation < 1:
            space_for_conversation = 1

        trimmed_conversation = conversation_msgs[-space_for_conversation:]
        self.conversation_history = system_msgs + trimmed_conversation

        self.logger.debug(
            "History truncated from %s to %s messages",
            original_size,
            len(self.conversation_history),
        )

    def chat_as_string(self, message: str) -> str:
        response = self.chat(message)
        return response.content

    def get_history_size(self) -> int:
        return len(self.conversation_history)

    def get_history_summary(self) -> Dict:
        return {
            "total_messages": len(self.conversation_history),
            "human_messages": sum(1 for msg in self.conversation_history if isinstance(msg, HumanMessage)),
            "ai_messages": sum(1 for msg in self.conversation_history if isinstance(msg, AIMessage)),
            "system_messages": sum(1 for msg in self.conversation_history if isinstance(msg, SystemMessage)),
            "tool_messages": sum(1 for msg in self.conversation_history if isinstance(msg, ToolMessage)),
            "max_history": self.config.max_history,
        }

    def get_history(self) -> List[BaseMessage]:
        return self.conversation_history.copy()

    def get_history_dict(self) -> List[Dict]:
        return [
            {
                "type": msg.__class__.__name__,
                "content": msg.content,
            }
            for msg in self.conversation_history
        ]

    def clear_history(self):
        self.logger.debug("Clearing conversation history")
        system_msgs = [msg for msg in self.conversation_history if isinstance(msg, SystemMessage)]
        self.conversation_history = system_msgs
