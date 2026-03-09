"""
Conversation orchestration for the career counselor chatbot.
"""

import logging
import os
from pathlib import Path
from typing import Generator, Optional

import anthropic
from jinja2 import Environment, FileSystemLoader

from .occupation_store import OccupationStore
from .onet_data import OnetStore
from .profile_search import ProfileSearch, load_profile_search
from .state_data import StateDataStore, load_state_data
from .tools import execute_tool, load_tool_definitions

logger = logging.getLogger(__name__)

# Max consecutive tool-use loops before forcing a text response
MAX_TOOL_ROUNDS = 10


class ChatbotError(Exception):
    """Base exception for chatbot errors."""
    pass


class APIError(ChatbotError):
    """Raised when the Claude API returns an error."""
    pass


class ToolExecutionError(ChatbotError):
    """Raised when a tool fails to execute."""
    pass


class CareerCounselorChatbot:
    """Career counselor chatbot powered by Claude with BLS and O*NET data tools."""

    def __init__(
        self,
        store: OccupationStore,
        state_store: StateDataStore,
        onet_store: Optional[OnetStore] = None,
        profile_search: Optional[ProfileSearch] = None,
    ):
        self.store = store
        self.state_store = state_store
        self.onet_store = onet_store
        self.profile_search = profile_search
        self.client = anthropic.Anthropic()
        self.model = "claude-opus-4-6"
        self.messages: list[dict] = []
        self.tools = load_tool_definitions(store, onet_store, profile_search)
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load system prompt from Jinja2 template."""
        templates_dir = Path(__file__).parent / "templates"
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("system_prompt.j2")

        return template.render(
            occupation_count=self.store.count,
            category_count=self.store.category_count,
            has_onet=self.onet_store is not None,
            has_profiles=self.profile_search is not None,
        )

    def _call_api(self) -> anthropic.types.Message:
        """Call the Claude API with error handling."""
        try:
            return self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=self.messages,
            )
        except anthropic.RateLimitError as e:
            logger.warning("Rate limited by Claude API: %s", e)
            raise APIError(
                "I'm getting too many requests right now. Please wait a moment and try again."
            ) from e
        except anthropic.APIConnectionError as e:
            logger.error("Cannot connect to Claude API: %s", e)
            raise APIError(
                "I'm having trouble connecting to my AI service. Please check your internet connection and try again."
            ) from e
        except anthropic.APITimeoutError as e:
            logger.error("Claude API timed out: %s", e)
            raise APIError(
                "The request took too long. Please try again with a shorter message."
            ) from e
        except anthropic.AuthenticationError as e:
            logger.error("Claude API authentication failed: %s", e)
            raise APIError(
                "There's an issue with the API key configuration. Please contact the administrator."
            ) from e
        except anthropic.APIStatusError as e:
            logger.error("Claude API error (status %d): %s", e.status_code, e)
            raise APIError(
                f"The AI service returned an error (status {e.status_code}). Please try again."
            ) from e

    def _execute_tool_safe(self, tool_name: str, tool_input: dict, tool_id: str) -> dict:
        """Execute a tool with error handling, returning a tool_result dict."""
        try:
            result = execute_tool(
                self.store, self.state_store, tool_name, tool_input,
                onet_store=self.onet_store,
                profile_search=self.profile_search,
            )
        except Exception as e:
            logger.error("Tool '%s' raised an exception: %s", tool_name, e, exc_info=True)
            result = f"Error executing {tool_name}: an internal error occurred. Please try a different query."
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": result,
        }

    def chat(self, user_message: str) -> str:
        """
        Send a message and get a response, handling tool calls.
        Returns the final assistant response text.
        Raises ChatbotError on failures.
        """
        self.messages.append({"role": "user", "content": user_message})

        for _round in range(MAX_TOOL_ROUNDS):
            response = self._call_api()

            # Check if we need to handle tool use
            if response.stop_reason == "tool_use":
                # Collect all tool uses and results
                assistant_content = response.content
                self.messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        tool_results.append(
                            self._execute_tool_safe(block.name, block.input, block.id)
                        )

                self.messages.append({"role": "user", "content": tool_results})
                # Continue the loop to get the final response

            else:
                # End turn - extract text response
                self.messages.append({"role": "assistant", "content": response.content})

                text_parts = []
                for block in response.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)

                return "\n".join(text_parts)

        # If we hit the limit, return whatever text we have from the last response
        logger.warning("Hit max tool rounds (%d) for message: %s", MAX_TOOL_ROUNDS, user_message[:100])
        return "I ran into an issue processing your request (too many data lookups). Could you try rephrasing your question?"

    def chat_stream(self, user_message: str) -> Generator[str, None, None]:
        """
        Send a message and stream the response.
        Yields text chunks as they arrive.
        Note: Tool calls are handled internally, only final text is streamed.
        Raises ChatbotError on failures.
        """
        self.messages.append({"role": "user", "content": user_message})

        for _round in range(MAX_TOOL_ROUNDS):
            response = self._call_api()

            if response.stop_reason == "tool_use":
                # Handle tool use
                assistant_content = response.content
                self.messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        tool_results.append(
                            self._execute_tool_safe(block.name, block.input, block.id)
                        )
                        # Yield a status message
                        yield f"\n[Looking up {block.name}...]\n"

                self.messages.append({"role": "user", "content": tool_results})
                # Continue loop

            else:
                # Final response - stream it
                self.messages.append({"role": "assistant", "content": response.content})

                for block in response.content:
                    if hasattr(block, "text"):
                        yield block.text

                return

        logger.warning("Hit max tool rounds (%d) in stream for message: %s", MAX_TOOL_ROUNDS, user_message[:100])
        yield "I ran into an issue processing your request (too many data lookups). Could you try rephrasing your question?"

    def reset(self):
        """Clear conversation history."""
        self.messages = []


def create_chatbot(db_path: str | None = None) -> CareerCounselorChatbot:
    """Create a chatbot instance with the career database loaded."""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "career_data.db")

    store = OccupationStore(db_path)
    state_store = load_state_data(db_path)

    # Load O*NET data if tables have data
    onet_store = None
    try:
        import sqlite3
        check = sqlite3.connect(db_path)
        count = check.execute("SELECT COUNT(*) FROM onet_occupations").fetchone()[0]
        check.close()
        if count > 0:
            from .onet_data import load_onet_data
            onet_store = load_onet_data(db_path)
    except Exception:
        pass

    # Load profile search if profiles have been generated
    profile_search = None
    try:
        profile_search = load_profile_search()
        if profile_search:
            logger.info("Profile search loaded: %d occupation profiles", profile_search.count)
    except Exception:
        logger.warning("Could not load profile search, continuing without it")

    return CareerCounselorChatbot(store, state_store, onet_store, profile_search)
