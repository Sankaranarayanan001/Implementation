import os
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()


class MCPClient:

    def __init__(self):
        self.session = None
        self.exit_stack = AsyncExitStack()

    async def connect(self):

        api_key = os.getenv("TRELLO_API_KEY")
        token = os.getenv("TRELLO_TOKEN")

        if not api_key:
            raise RuntimeError("TRELLO_API_KEY is missing from .env")

        if not token:
            raise RuntimeError("TRELLO_TOKEN is missing from .env")

        env = os.environ.copy()
        env["TRELLO_API_KEY"] = api_key
        env["TRELLO_TOKEN"] = token

        server_params = StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@delorenj/mcp-server-trello"
            ],
            env=env
        )

        transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        read, write = transport

        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        await self.session.initialize()

        print("Connected to Trello MCP server")

    async def get_tools(self):

        response = await self.session.list_tools()

        return response.tools

    async def call_tool(self, tool_name, arguments):

        return await self.session.call_tool(
            tool_name,
            arguments
        )

    async def cleanup(self):

        await self.exit_stack.aclose()