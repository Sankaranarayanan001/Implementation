import asyncio
import json

from openai import OpenAI
from client import MCPRouter  # <-- reusing your existing mediator, unchanged

# Ollama's OpenAI-compatible endpoint. api_key is required by the SDK but
# ignored by Ollama since everything runs locally — any string works.
ollama = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
MODEL = "qwen2.5:3b-instruct"  # must be a model you've already `ollama pull`ed


async def run_agent_turn(router: MCPRouter, tools: list, messages: list) -> str:
    """
    Sends the conversation + tool list to the local Ollama server. If the
    model responds with tool_calls, runs each one through router.call()
    (your existing MCP routing logic, untouched) and appends the result
    as a role="tool" message, looping until the model returns plain text.
    """
    while True:
        response = ollama.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content or ""

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            print(f"  [calling tool: {tc.function.name}({args})]")
            result_text = await router.call(tc.function.name, args)  # your existing method
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result_text}
            )
        # loop again so the model can use the tool result(s), or ask for more


async def main():
    router = MCPRouter()
    await router.connect_all()

    # Build the tool schema directly from what connect_all() already
    # discovered, without modifying MCPRouter itself.
    tools = []
    for name, session in router.sessions.items():
        listed = await session.list_tools()
        for tool in listed.tools:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                }
            )

    print("Connected tools:", ", ".join(router.tool_map.keys()))
    messages = [
        {"role": "system", "content": "You are a helpful assistant with access to tools. Use them when needed."}
    ]

    try:
        while True:
            user_input = input("\nYou: ").strip()
            if user_input.lower() in ("quit", "exit"):
                break

            messages.append({"role": "user", "content": user_input})
            answer = await run_agent_turn(router, tools, messages)
            print(f"\nOllama: {answer}")
    finally:
        await router.close()


if __name__ == "__main__":
    asyncio.run(main())