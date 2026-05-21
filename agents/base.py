import json
from typing import Any
import anthropic
from rich.console import Console

console = Console()


class BaseAgent:
    def __init__(self, client: anthropic.Anthropic, model: str = None):
        self.client = client
        import config
        self.model = model or config.MODEL

    def _execute_tool(self, name: str, inputs: dict) -> Any:
        raise NotImplementedError(f"Tool not implemented: {name}")

    def run(self, initial_message: str, system: str, tools: list, max_iterations: int = 20) -> str:
        messages = [{"role": "user", "content": initial_message}]
        final_text = ""

        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=tools,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text = block.text
                break

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    preview = ", ".join(
                        f"{k}={repr(v)[:40]}" for k, v in block.input.items()
                        if k not in ("content", "research_brief", "edit_notes")
                    )
                    console.print(f"  [dim]→ {block.name}({preview})[/dim]")
                    try:
                        result = self._execute_tool(block.name, block.input)
                    except Exception as e:
                        result = {"error": str(e)}

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result) if not isinstance(result, str) else result,
                    })

            messages.append({"role": "user", "content": tool_results})

        return final_text
