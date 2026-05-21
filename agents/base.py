import json
from typing import Any
from rich.console import Console

console = Console()


class BaseAgent:
    def __init__(self, client, model: str = None):
        self.client = client
        import config as cfg
        self.provider = cfg.PROVIDER
        self.model = model or cfg.MODEL

    def _execute_tool(self, name: str, inputs: dict) -> Any:
        raise NotImplementedError(f"Tool not implemented: {name}")

    def run(self, initial_message: str, system: str, tools: list, max_iterations: int = 20) -> str:
        if self.provider in ("groq", "ollama"):
            return self._run_openai(initial_message, system, tools, max_iterations)
        return self._run_anthropic(initial_message, system, tools, max_iterations)

    # ── Anthropic path ────────────────────────────────────────────────────────

    def _run_anthropic(self, initial_message, system, tools, max_iterations):
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
                    _log_tool(block.name, block.input)
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

    # ── OpenAI-compatible path (Groq, Ollama, etc.) ───────────────────────────

    def _run_openai(self, initial_message, system, tools, max_iterations):
        oai_tools = _to_openai_tools(tools)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": initial_message},
        ]
        final_text = ""

        for _ in range(max_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=8192,
                tools=oai_tools,
                messages=messages,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            # Append as dict so it serialises cleanly across loop iterations
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})

            if not msg.tool_calls:
                final_text = msg.content or ""
                break

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    inputs = json.loads(tc.function.arguments)
                except Exception:
                    inputs = {}
                _log_tool(name, inputs)
                try:
                    result = self._execute_tool(name, inputs)
                except Exception as e:
                    result = {"error": str(e)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result) if not isinstance(result, str) else result,
                })

        return final_text


def _to_openai_tools(tools: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _log_tool(name: str, inputs: dict):
    preview = ", ".join(
        f"{k}={repr(v)[:40]}"
        for k, v in inputs.items()
        if k not in ("content", "research_brief", "edit_notes")
    )
    console.print(f"  [dim]→ {name}({preview})[/dim]")
