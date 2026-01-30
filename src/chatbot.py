"""
Conversation orchestration for the career counselor chatbot.
"""

import os
from pathlib import Path
from typing import Generator

import anthropic
from jinja2 import Environment, FileSystemLoader

from .occupation_store import OccupationStore
from .state_data import StateDataStore, load_state_data
from .tools import execute_tool, load_tool_definitions


class CareerCounselorChatbot:
    """Career counselor chatbot powered by Claude with BLS data tools."""

    def __init__(self, store: OccupationStore, state_store: StateDataStore):
        self.store = store
        self.state_store = state_store
        self.client = anthropic.Anthropic()
        self.model = "claude-opus-4-5-20251101"
        self.messages: list[dict] = []
        self.tools = load_tool_definitions(store)
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load system prompt from Jinja2 template."""
        templates_dir = Path(__file__).parent / "templates"
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("system_prompt.j2")

        return template.render(
            occupation_count=self.store.count,
            category_count=self.store.category_count,
        )

    def chat(self, user_message: str) -> str:
        """
        Send a message and get a response, handling tool calls.
        Returns the final assistant response text.
        """
        self.messages.append({"role": "user", "content": user_message})

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=self.messages,
            )

            # Check if we need to handle tool use
            if response.stop_reason == "tool_use":
                # Collect all tool uses and results
                assistant_content = response.content
                self.messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        result = execute_tool(self.store, self.state_store, block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

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

    def chat_stream(self, user_message: str) -> Generator[str, None, None]:
        """
        Send a message and stream the response.
        Yields text chunks as they arrive.
        Note: Tool calls are handled internally, only final text is streamed.
        """
        self.messages.append({"role": "user", "content": user_message})

        while True:
            # First, make a non-streaming call to check for tool use
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=self.messages,
            )

            if response.stop_reason == "tool_use":
                # Handle tool use
                assistant_content = response.content
                self.messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        result = execute_tool(self.store, self.state_store, block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
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

                break

    def reset(self):
        """Clear conversation history."""
        self.messages = []


def create_chatbot(xml_path: str | None = None, xlsx_path: str | None = None) -> CareerCounselorChatbot:
    """Create a chatbot instance with the BLS data loaded."""
    data_dir = Path(__file__).parent.parent / "data"

    if xml_path is None:
        xml_path = data_dir / "xml-compilation.xml"
    if xlsx_path is None:
        xlsx_path = data_dir / "state_M2024_dl.xlsx"

    store = OccupationStore(str(xml_path))
    state_store = load_state_data(str(xlsx_path))

    return CareerCounselorChatbot(store, state_store)
