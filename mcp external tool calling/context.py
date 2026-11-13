# context.py

class TrelloContext:
    def __init__(self):
        # Store Trello entities as:
        # name -> ID
        self.boards = {}
        self.lists = {}
        self.cards = {}

    # -------------------------
    # BOARD
    # -------------------------

    def save_board(self, name, board_id):
        """Save a board name and its Trello ID."""
        if name and board_id:
            self.boards[name.lower()] = board_id

    def get_board_id(self, name):
            if not name:
                return None

            normalized_name = (
        str(name)
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .strip()
    )

            return self.boards.get(normalized_name)

    # -------------------------
    # LIST
    # -------------------------

    def save_list(self, name, list_id):
        """Save a list name and its Trello ID."""
        if name and list_id:
            self.lists[name.lower()] = list_id

    def get_list_id(self, name):
        if not name:
            return None

        normalized_name = (
        str(name)
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .strip()
    )

        return self.lists.get(normalized_name)

    # -------------------------
    # CARD
    # -------------------------

    def save_card(self, name, card_id):
        """Save a card name and its Trello ID."""
        if name and card_id:
            self.cards[name.lower()] = card_id

    def get_card_id(self, name):
        if not name:
            return None

        normalized_name = (
        str(name)
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .strip()
    )

        return self.cards.get(normalized_name)

    # -------------------------
    # DEBUG / VIEW
    # -------------------------

    def show_context(self):
        """Show all saved entities."""
        print("\nSaved Trello Context:")

        print("\nBoards:")
        for name, board_id in self.boards.items():
            print(f"  {name} -> {board_id}")

        print("\nLists:")
        for name, list_id in self.lists.items():
            print(f"  {name} -> {list_id}")

        print("\nCards:")
        for name, card_id in self.cards.items():
            print(f"  {name} -> {card_id}")