from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Union
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    BaseMessage,
    ToolMessage
)

from agents.agent_config import AgentConfig

class BaseAgent(ABC):
    """
    Abstract base class for all agents
    """
    
    def __init__(self, config: Optional[AgentConfig] = None, system_prompt: Optional[str] = None):
        """
        Initialize base agent
        """
        self.config = config or AgentConfig()
        self.model = ChatGoogleGenerativeAI(
            model=self.config.model_name,
            api_key=self.config.api_key,
            temperature=self.config.temperature
        )
        
        # History conversation
        self.conversation_history : List[BaseMessage] = []
        
        # Add system prompt if provided 
        if system_prompt:
            self.conversation_history.append(SystemMessage(content=system_prompt))

    
    def chat(self, message: str) -> BaseMessage:
        """
        Send new message and get response (returns BaseMessage to capture tool calls)
        """
        
        # Add Human message 
        human_msg = HumanMessage(content=message)
        self.conversation_history.append(human_msg)
        
        # Get response from model
        response = self.model.invoke(self.conversation_history)
        
        # Add new response in conversation 
        self.conversation_history.append(response)
        
        # Keep history limited
        self._truncate_history_smart()
        
        return response
    
    
    def _truncate_history(self):
        """
        Basic truncation: Keep only the most recent messages
        Removes oldest messages when exceeding max_history
        """
        if len(self.conversation_history) > self.config.max_history:
            self.conversation_history = self.conversation_history[-self.config.max_history:]
    
    
    def _truncate_history_smart(self):
        """
        Smart truncation: ALWAYS preserve ALL SystemMessages, remove oldest non-system messages
        
        Rule: SystemMessages are NEVER removed - they're the foundation of agent behavior.
        Only trim oldest conversation messages (Human, AI, Tool) if needed.
        """
        if len(self.conversation_history) <= self.config.max_history:
            return
        
        # Step 1: Extract all system messages (always keep these)
        system_msgs = [msg for msg in self.conversation_history 
                       if isinstance(msg, SystemMessage)]
        
        # Step 2: Extract conversation messages
        conversation_msgs = [msg for msg in self.conversation_history 
                            if not isinstance(msg, SystemMessage)]
        
        # Step 3: Calculate space left for conversation
        space_for_conversation = self.config.max_history - len(system_msgs)
        
        # Step 4: Ensure we keep at least 1 conversation message
        if space_for_conversation < 1:
            space_for_conversation = 1
        
        # Step 5: Keep most recent conversation messages
        trimmed_conversation = conversation_msgs[-space_for_conversation:]
        
        # Step 6: Rebuild history (system messages first, then conversation)
        self.conversation_history = system_msgs + trimmed_conversation
    
    
    def chat_as_string(self, message: str) -> str:
        """
        Convenience method: Send message and return just the text content
        
        Args:
            message: User message
            
        Returns:
            str: Just the text content of AI response
        """
        response = self.chat(message)
        return response.content
        
    
    def get_history_size(self) -> int:
        """Get current history message count"""
        return len(self.conversation_history)
    
    
    def get_history_summary(self) -> Dict:
        """Get summary statistics of conversation history"""
        return {
            "total_messages": len(self.conversation_history),
            "human_messages": sum(1 for msg in self.conversation_history if isinstance(msg, HumanMessage)),
            "ai_messages": sum(1 for msg in self.conversation_history if isinstance(msg, AIMessage)),
            "system_messages": sum(1 for msg in self.conversation_history if isinstance(msg, SystemMessage)),
            "tool_messages": sum(1 for msg in self.conversation_history if isinstance(msg, ToolMessage)),
            "max_history": self.config.max_history
        }
    
    
    def get_history(self) -> List[BaseMessage]:
        """Get full conversation history"""
        return self.conversation_history.copy()
    
    
    def get_history_dict(self) -> List[Dict]:
        """Convert conversation history to dictionaries for serialization"""
        return [
            {
                "type": msg.__class__.__name__,
                "content": msg.content
            }
            for msg in self.conversation_history
        ]
    
    
    def clear_history(self):
        """Clear conversation history (keeps system prompt if exists)"""
        system_msgs = [msg for msg in self.conversation_history if isinstance(msg, SystemMessage)]
        self.conversation_history = system_msgs