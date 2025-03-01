from typing import List, Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationManager:
    """
    Manages conversation history and context for LLM interactions.
    Handles history pruning, context window management, and state tracking.
    """
    
    def __init__(self, max_history: int = 10):
        self.conversation_history = []
        self.max_history = max_history
        self.session_state = {}
        self.system_message = None
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation history"""
        self.conversation_history.append({
            "role": "user",
            "content": content
        })
        self._prune_history()
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation history"""
        self.conversation_history.append({
            "role": "assistant",
            "content": content
        })
        self._prune_history()
    
    def add_tool_result(self, tool_name: str, result: str) -> None:
        """Add a tool result to the conversation history"""
        self.conversation_history.extend([
            {"role": "assistant", "content": f"Using {tool_name}..."},
            {"role": "user", "content": result}
        ])
        self._prune_history()
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Get the current conversation history"""
        return self.conversation_history.copy()
    
    def _prune_history(self) -> None:
        """Prune conversation history if it exceeds max length"""
        if len(self.conversation_history) > self.max_history:
            # Keep system message if present, then most recent messages
            system_messages = []
            if self.conversation_history and self.conversation_history[0]["role"] == "system":
                system_messages = [self.conversation_history[0]]
            
            recent_messages = self.conversation_history[-(self.max_history-len(system_messages)):]
            self.conversation_history = system_messages + recent_messages
    
    def set_system_message(self, system_prompt: str) -> None:
        """Set the system message for the conversation"""
        self.system_message = system_prompt
    
    def clear_history(self, keep_system: bool = True) -> None:
        """Clear conversation history, optionally keeping system message"""
        if keep_system and self.conversation_history and self.conversation_history[0]["role"] == "system":
            system_message = self.conversation_history[0]
            self.conversation_history = [system_message]
        else:
            self.conversation_history = []
    
    def update_session_state(self, key: str, value: Any) -> None:
        """Update session state with key-value pair"""
        self.session_state[key] = value
    
    def get_session_state(self, key: str, default: Optional[Any] = None) -> Any:
        """Get value from session state"""
        return self.session_state.get(key, default)
    
    def get_system_message(self) -> Optional[str]:
        """Get the system message"""
        return self.system_message 