import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Map: server name -> how to launch it
SERVERS = {
    "search": StdioServerParameters(command="python", args=["web_server.py"]),
    "api": StdioServerParameters(command="python", args=["api_server.py"]),
    "files": StdioServerParameters(command="python", args=["files_server.py"]),
}

# Which arguments each tool expects, so we know what to prompt the user for.
TOOL_ARGS = {
    "web_search": ["query"],
    "get_weather": ["city"],
    "write_file": ["filename", "content"],
    "read_file": ["filename"],
    
}

class MCPRouter:
    def __init__(self):
        self.sessions = {}      # server_name -> ClientSession
        self.tool_map = {}      # tool_name -> server_name
        self._stack = None

    async def connect_all(self):
        from contextlib import AsyncExitStack
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        for name, params in SERVERS.items():
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions[name] = session

            tools = await session.list_tools()
            for tool in tools.tools:
                self.tool_map[tool.name] = name   # register which server owns this tool

    async def call(self, tool_name: str, arguments: dict):
        server_name = self.tool_map.get(tool_name)
        if not server_name:
            return f"No server has a tool named '{tool_name}'"
        session = self.sessions[server_name]
        result = await session.call_tool(tool_name, arguments)
        return result.content[0].text

    async def close(self):
        await self._stack.__aexit__(None, None, None)


async def main():
    router = MCPRouter()
    await router.connect_all()

    tool_names = list(router.tool_map.keys())

    try:
        while True:
            print("\nAvailable tools:")
            for i, name in enumerate(tool_names, start=1):
                print(f"  {i}. {name}")
            print("  0. Quit")

            choice = input("\nPick a tool by number: ").strip()
            if choice == "0":
                break
            if not choice.isdigit() or not (1 <= int(choice) <= len(tool_names)):
                print("Invalid choice, try again.")
                continue

            tool_name = tool_names[int(choice) - 1]
            arguments = {}
            for arg_name in TOOL_ARGS.get(tool_name, []):
                arguments[arg_name] = input(f"  {arg_name}: ").strip()

            result = await router.call(tool_name, arguments)
            print("\nResult:")
            print(result)
    finally:
        await router.close()

if __name__ == "__main__":
    asyncio.run(main())