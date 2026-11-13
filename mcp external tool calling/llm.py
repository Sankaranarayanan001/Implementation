import json

from ollama import AsyncClient

from context import TrelloContext
from router import (
    classify_intent,
    get_tools_for_intent
)


MODEL = "qwen2.5"

ollama = AsyncClient()


# ---------------------------------------
# MEMORY / CONTEXT
# ---------------------------------------

context = TrelloContext()


# ---------------------------------------
# CONVERT MCP TOOLS FOR OLLAMA
# ---------------------------------------

def convert_tools(tools):

    converted = []

    for tool in tools:

        converted.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema
            }
        })

    return converted


# ---------------------------------------
# EXTRACT MCP TEXT
# ---------------------------------------

def extract_tool_result(result):

    parts = []

    for item in result.content:

        if hasattr(item, "text"):
            parts.append(item.text)

    return "\n".join(parts)


# ---------------------------------------
# PARSE JSON
# ---------------------------------------

def parse_json(text):

    try:
        return json.loads(text)

    except Exception:

        # Try removing markdown code fences
        cleaned = text.strip()

        if cleaned.startswith("```"):

            cleaned = cleaned.replace(
                "```json",
                ""
            ).replace(
                "```",
                ""
            ).strip()

            try:
                return json.loads(cleaned)

            except Exception:
                return None

        return None


# ---------------------------------------
# GET ENTITY LIST
# ---------------------------------------

def get_items(data, key):

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        if key in data:

            value = data[key]

            if isinstance(value, list):
                return value

        # Sometimes MCP returns one object
        if (
            data.get("id")
            and data.get("name")
        ):
            return [data]

    return []


# ---------------------------------------
# SAVE BOARDS
# ---------------------------------------

def save_boards_from_result(result_text):

    data = parse_json(result_text)

    if data is None:
        return

    boards = get_items(
        data,
        "boards"
    )

    for board in boards:

        if not isinstance(board, dict):
            continue

        board_id = board.get("id")
        board_name = board.get("name")

        if board_id and board_name:

            context.save_board(
                board_name,
                board_id
            )

            print(
                f"Saved board: "
                f"{board_name} -> {board_id}"
            )


# ---------------------------------------
# FORMAT BOARDS
# ---------------------------------------

def format_boards(result_text):

    data = parse_json(result_text)

    if data is None:
        return "I couldn't read the board information."

    boards = get_items(
        data,
        "boards"
    )

    names = []

    for board in boards:

        if not isinstance(board, dict):
            continue

        name = board.get("name")

        if name:
            names.append(name)

    if not names:
        return "You don't have any Trello boards."

    return "\n".join(names)


# ---------------------------------------
# SAVE LISTS
# ---------------------------------------

def save_lists_from_result(result_text):

    data = parse_json(result_text)

    if data is None:
        return

    lists = get_items(
        data,
        "lists"
    )

    for item in lists:

        if not isinstance(item, dict):
            continue

        list_id = item.get("id")
        list_name = item.get("name")

        if list_id and list_name:

            context.save_list(
                list_name,
                list_id
            )

            print(
                f"Saved list: "
                f"{list_name} -> {list_id}"
            )


# ---------------------------------------
# FORMAT LISTS
# ---------------------------------------

def format_lists(result_text):

    data = parse_json(result_text)

    if data is None:
        return "I couldn't read the list information."

    lists = get_items(
        data,
        "lists"
    )

    names = []

    for item in lists:

        if not isinstance(item, dict):
            continue

        name = item.get("name")

        if name:
            names.append(name)

    if not names:
        return "There are no lists in this board."

    return "\n".join(names)


# ---------------------------------------
# SAVE CARD
# ---------------------------------------

def save_card_from_result(result_text):

    data = parse_json(result_text)

    if data is None:
        return

    if not isinstance(data, dict):
        return

    card_id = data.get("id")
    card_name = data.get("name")

    if card_id and card_name:

        context.save_card(
            card_name,
            card_id
        )

        print(
            f"Saved card: "
            f"{card_name} -> {card_id}"
        )


# ---------------------------------------
# FORMAT CARD RESULT
# ---------------------------------------

def format_card_result(
    tool_name,
    result_text
):

    data = parse_json(result_text)

    if data is None:
        return "The Trello operation was completed."

    if not isinstance(data, dict):
        return "The Trello operation was completed."

    card_name = data.get("name")

    if tool_name == "add_card_to_list":

        if card_name:
            return (
                f"Done. Card '{card_name}' "
                f"was added successfully."
            )

        return "Done. The card was added successfully."

    if tool_name == "update_card_details":

        if card_name:
            return (
                f"Done. The card was updated "
                f"to '{card_name}'."
            )

        return "Done. The card was updated successfully."

    return "The Trello operation was completed."


# ---------------------------------------
# HUMAN RESPONSE
# ---------------------------------------

async def generate_human_response(
    prompt,
    tool_result,
    operation_type
):

    if operation_type == "boards":
        return format_boards(tool_result)

    if operation_type == "lists":
        return format_lists(tool_result)

    if operation_type == "card":
        return format_card_result(
            operation_type,
            tool_result
        )

    response = await ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": """
You are a helpful Trello assistant.

Convert the provided result into a short,
natural, human-friendly response.

STRICT RULES:

- Never return JSON.
- Never return Python dictionaries.
- Never return raw MCP results.
- Never show Trello IDs.
- Never show internal tool names.
- Never mention MCP.
- Never mention JSON.
- Never mention internal processing.
- Never invent information.
- Use only information contained in the tool result.
- Keep the answer concise.
- Speak naturally like a human assistant.

For example:

User:
Show my boards

Response:
Here are your Trello boards:
AI Project
My Trello board
Website Development

User:
Show the lists in AI Project

Response:
The lists in AI Project are:
To Do
Doing
Done

User:
Add a card called Login Page to To Do

Response:
Done. I added 'Login Page' to the To Do list.

User:
Rename Login Page to User Login Page

Response:
Done. I renamed 'Login Page' to 'User Login Page'.
"""
            },
            {
                "role": "user",
                "content": prompt
            },
            {
                "role": "tool",
                "content": tool_result
            }
        ]
    )

    answer = response["message"]["content"].strip()

    # ---------------------------------------
    # BASIC JSON PROTECTION
    # ---------------------------------------

    parsed = parse_json(answer)

    if parsed is not None:

        return "The Trello operation was completed successfully."

    return answer


# ---------------------------------------
# PROCESS PROMPT
# ---------------------------------------

async def process_prompt(
    prompt,
    mcp_tools,
    session
):

    # ---------------------------------------
    # STEP 1: INTENT
    # ---------------------------------------

    intent = await classify_intent(prompt)

    print(
        f"\nDetected intent: {intent}"
    )


    # ---------------------------------------
    # STEP 2: CONVERSATIONAL
    # ---------------------------------------

    if intent == "conversational":

        response = await ollama.chat(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """
You are a helpful Trello assistant.

Answer conversational questions naturally.

IMPORTANT:
- Never return JSON.
- Never return Python dictionaries.
- Never discuss MCP.
- Never discuss tool calls.
- Never discuss internal implementation.
- Keep the response natural and concise.
"""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        answer = response["message"]["content"].strip()

        parsed = parse_json(answer)

        if parsed is not None:
            return "I'm here to help with your Trello tasks."

        return answer


    # ---------------------------------------
    # STEP 3: SELECT RELEVANT TOOLS
    # ---------------------------------------

    selected_tools = get_tools_for_intent(
        mcp_tools,
        intent,
        prompt
    )

    print(
        f"Available tools for '{intent}': "
        f"{len(selected_tools)}"
    )

    print("Selected tools:")

    for tool in selected_tools:
        print(f"- {tool.name}")


    if not selected_tools:
        return "I couldn't find a suitable Trello operation."


    # ---------------------------------------
    # STEP 4: CONVERT TOOLS
    # ---------------------------------------

    tools = convert_tools(
        selected_tools
    )


    # ---------------------------------------
    # STEP 5: QWEN TOOL SELECTION
    # ---------------------------------------

    messages = [
        {
            "role": "system",
            "content": """
You are a Trello assistant.

Use only the provided Trello tools.

IMPORTANT RULES:

1. Never invent IDs.

2. Never create fake Trello IDs.

3. When the user gives a board name,
   use the board name in the boardId argument.
   The application will convert it to the real ID.

4. When the user gives a list name,
   put the exact list NAME in the listId argument.
   The application will convert it to the real ID.

   IMPORTANT:
   - Never use "_id" or "_list_id" in the listId value.
   - Never use values such as "to_do_list_id",
     "doing_list_id", or "done_list_id".
   - If the user says "To Do", use exactly "To Do".
   - If the user says "Doing", use exactly "Doing".
   - If the user says "Done", use exactly "Done".
   - Do not convert list names to snake_case.

5. When the user gives a card name,
   use the card name in the cardId argument.
   The application will convert it to the real ID.

6. Never return JSON as the final user response.

7. Never show raw MCP results.

8. Never show Trello IDs to the user.

9. Never invent information.

10. If the application resolves a name to an ID,
    use the resolved ID when calling Trello.

11. For update_card_details,
    cardId should initially contain the card NAME
    provided by the user, not an invented ID.

12. Keep tool arguments accurate and minimal.
"""
        },
        {
            "role": "user",
            "content": prompt
        }
    ]


    # ---------------------------------------
    # STEP 6: TOOL LOOP
    # ---------------------------------------

    for iteration in range(5):

        response = await ollama.chat(
            model=MODEL,
            messages=messages,
            tools=tools
        )

        message = response["message"]

        

        tool_calls = message.get(
            "tool_calls",
            []
        )


        # ---------------------------------------
        # NO TOOL CALL
        # ---------------------------------------

        if not tool_calls:

            answer = message.get(
                "content",
                ""
            ).strip()

            if not answer:
                return "I couldn't complete that Trello request."

            # Never allow JSON to reach the user
            parsed = parse_json(answer)

            if parsed is not None:
                return "I couldn't generate a human-readable response."

            return answer


        messages.append(message)


        # ---------------------------------------
        # EXECUTE TOOL CALLS
        # ---------------------------------------

        for call in tool_calls:

            tool_name = call[
                "function"
            ]["name"]

            arguments = call[
                "function"
            ]["arguments"]

        
            # ---------------------------------------
            # SAFETY: TOOL MUST BE SELECTED
            # ---------------------------------------

            allowed_names = {
                tool.name
                for tool in selected_tools
            }

            if tool_name not in allowed_names:

                return (
                    "I couldn't complete that "
                    "Trello operation."
                )


            # ---------------------------------------
            # RESOLVE BOARD ID
            # ---------------------------------------

            if tool_name == "get_lists":

                board_name = arguments.get(
                    "boardId"
                )

                saved_board_id = (
                    context.get_board_id(
                        board_name
                    )
                )

                print(
                    f"Board lookup: "
                    f"'{board_name}' -> "
                    f"'{saved_board_id}'"
                )

                if not saved_board_id:

                    return (
                        f"I don't have the ID "
                        f"for board '{board_name}'. "
                        f"Please list the boards first."
                    )

                arguments["boardId"] = (
                    saved_board_id
                )

                print(
                    f"Resolved board: "
                    f"{board_name} -> "
                    f"{saved_board_id}"
                )


            # ---------------------------------------
            # RESOLVE LIST ID
            # ---------------------------------------

            if tool_name == "add_card_to_list":

                list_name = arguments.get("listId", "")

                normalized_list_name = (
                    str(list_name)
                    .lower()
                    .replace("_", " ")
                    .replace("-", " ")
                    .strip()
                )

                saved_list_id = context.get_list_id(
                    normalized_list_name
                )

                print(
                    f"List lookup: "
                    f"'{list_name}' -> "
                    f"'{saved_list_id}'"
                )

                if not saved_list_id:

                    return (
                        f"I don't have the ID "
                        f"for list '{list_name}'. "
                        f"Please show the lists first."
                    )

                arguments["listId"] = (
                    saved_list_id
                )

                print(
                    f"Resolved list: "
                    f"{list_name} -> "
                    f"{saved_list_id}"
                )


            # ---------------------------------------
            # RESOLVE CARD ID
            # ---------------------------------------

            if tool_name == "update_card_details":

                card_name = arguments.get(
                    "cardId"
                )

                saved_card_id = (
                    context.get_card_id(
                        card_name
                    )
                )

                print(
                    f"Card lookup: "
                    f"'{card_name}' -> "
                    f"'{saved_card_id}'"
                )

                if not saved_card_id:

                    return (
                        f"I don't have the ID "
                        f"for card '{card_name}'. "
                        f"Please create the card first."
                    )

                arguments["cardId"] = (
                    saved_card_id
                )

                print(
                    f"Resolved card: "
                    f"{card_name} -> "
                    f"{saved_card_id}"
                )


            # ---------------------------------------
            # CALL MCP
            # ---------------------------------------

            try:

                print("Tool:", tool_name)
                print("Arguments:", arguments)


                result = await session.call_tool(
                    tool_name,
                    arguments
                )

                result_text = (
                    extract_tool_result(result)
                )

                # ---------------------------------------
                # CHECK FOR MCP ERROR
                # ---------------------------------------

                if (
                    result_text.startswith(
                        "Error:"
                    )
                    or "MCP error" in result_text
                    or "Request failed" in result_text
                ):

                    return (
                        "The Trello operation "
                        "failed. Please check the "
                        "requested board, list, or card."
                    )


                # ---------------------------------------
                # SAVE CONTEXT
                # ---------------------------------------

                if tool_name == "list_boards":

                    save_boards_from_result(
                        result_text
                    )

                    return format_boards(
                        result_text
                    )


                if tool_name == "get_lists":

                    save_lists_from_result(
                        result_text
                    )

                    return format_lists(
                        result_text
                    )


                if tool_name == "add_card_to_list":

                    # Save the newly created card so it can be
                    # referenced later for update operations.
                    save_card_from_result(
                        result_text
                    )

                    return format_card_result(
                        tool_name,
                        result_text
                    )


                if tool_name == "update_card_details":

                    # Save the updated card name
                    save_card_from_result(
                        result_text
                    )

                    return format_card_result(
                        tool_name,
                        result_text
                    )


                if tool_name == "create_board":

                    save_boards_from_result(
                        result_text
                    )

                    data = parse_json(
                        result_text
                    )

                    if (
                        isinstance(data, dict)
                        and data.get("name")
                    ):

                        return (
                            f"Done. Board "
                            f"'{data['name']}' "
                            f"was created successfully."
                        )

                    return (
                        "Done. The board was "
                        "created successfully."
                    )


                # ---------------------------------------
                # SEND SUCCESSFUL RESULT TO QWEN
                # ---------------------------------------

                messages.append({
                    "role": "tool",
                    "content": result_text
                })


            except Exception as e:

                print(
                    f"Tool execution failed: {e}"
                )

                return (
                    "The Trello operation "
                    "failed."
                )


    return (
        "I couldn't complete the Trello request."
    )