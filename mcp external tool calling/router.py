from ollama import AsyncClient


MODEL = "qwen2.5"

ollama = AsyncClient()


# ---------------------------------------
# ONLY THESE 5 TOOLS ARE ALLOWED
# ---------------------------------------

ALLOWED_TOOLS = {
    "list_boards",
    "create_board",
    "get_lists",
    "add_card_to_list",
    "update_card_details",
}


# ---------------------------------------
# INTENT CLASSIFICATION
# ---------------------------------------

async def classify_intent(prompt):

    response = await ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": """
Classify the user's Trello request into exactly ONE category.

Categories:

query
action
update
conversational

Rules:

query:
- list boards
- show boards
- get lists
- show lists

action:
- create a board
- add a card

update:
- update a card
- change a card
- rename a card

conversational:
- greetings
- general conversation
- unrelated requests

Examples:

"List all my Trello boards"
=query

"Show my boards"
=query

"Show the lists in AI Project"
=query

"Create a board called AI Project"
=action

"Add a Login Page card to Backlog"
=action

"Rename Login Page to User Login Page"
=update

"Hello"
=conversational

Return ONLY:
query
action
update
conversational
"""
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    intent = response["message"]["content"].strip().lower()

    # Remove accidental formatting such as:
# =query
# =action
# =update
# =conversational
    intent = intent.lstrip("=").strip()

    print(f"Intent classifier response: {intent}")

    allowed_intents = {
        "query",
        "action",
        "update",
        "conversational"
    }

    if intent not in allowed_intents:
        return "conversational"

    return intent

    


# ---------------------------------------
# TOOL SELECTION
# ---------------------------------------

def get_tools_for_intent(
    mcp_tools,
    intent,
    prompt
):

    prompt_lower = prompt.lower()

    # ---------------------------------------
    # QUERY
    # ---------------------------------------

    if intent == "query":

        # User is asking for boards
        if (
            "board" in prompt_lower
            and any(
                word in prompt_lower
                for word in [
                    "list",
                    "show",
                    "what",
                    "all",
                    "my"
                ]
            )
        ):

            allowed_names = {
                "list_boards"
            }

        # User is asking for lists
        elif (
            "list" in prompt_lower
            or "lists" in prompt_lower
        ):

            allowed_names = {
                "get_lists"
            }

        else:

            allowed_names = {
                "list_boards",
                "get_lists"
            }

    # ---------------------------------------
    # ACTION
    # ---------------------------------------

    elif intent == "action":

        if (
            "card" in prompt_lower
            or "add" in prompt_lower
            or "create card" in prompt_lower
        ):

            allowed_names = {
                "add_card_to_list"
            }

        else:

            allowed_names = {
                "create_board"
            }

    # ---------------------------------------
    # UPDATE
    # ---------------------------------------

    elif intent == "update":

        allowed_names = {
            "update_card_details"
        }

    else:

        allowed_names = set()

    return [
        tool
        for tool in mcp_tools
        if tool.name in allowed_names
        and tool.name in ALLOWED_TOOLS
    ]