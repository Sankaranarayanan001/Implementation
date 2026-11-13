import asyncio

from client import MCPClient
from llm import process_prompt


async def main():

    client = MCPClient()

    try:

        # Connect to Trello MCP
        await client.connect()

        # Get all tools from MCP server
        all_tools = await client.get_tools()

        print(
            f"\nMCP server provides "
            f"{len(all_tools)} tools."
        )

        # --------------------------------
        # ONLY USE THESE 5 TOOLS
        # --------------------------------

        allowed_tools = {
            "list_boards",
            "create_board",
            "get_lists",
            "add_card_to_list",
            "update_card_details"
        }

        mcp_tools = [
            tool
            for tool in all_tools
            if tool.name in allowed_tools
        ]

        print(
            f"Our application is using "
            f"{len(mcp_tools)} tools."
        )

        for tool in mcp_tools:
            print(f"- {tool.name}")

        print(
            "\nTrello MCP + Qwen is ready."
        )

        # --------------------------------
        # INTERACTIVE LOOP
        # --------------------------------

        while True:

            prompt = input("\nYou: ").strip()

            if not prompt:
                continue

            if prompt.lower() in {
                "exit",
                "quit"
            }:
                break

            try:

                answer = await process_prompt(
                    prompt,
                    mcp_tools,
                    client.session
                )

                print(
                    f"\nAssistant: {answer}"
                )

            except Exception as e:

                print(
                    f"\nError: {e}"
                )

    finally:

        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())