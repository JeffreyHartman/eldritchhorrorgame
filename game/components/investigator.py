from typing import Dict, List


class Investigator:
    def __init__(
        self,
        name: str,
        health: int,
        max_health: int,
        sanity: int,
        max_sanity: int,
        skills: Dict[str, int],
        items: List[str],
        clue_tokens: int,
        train_tickets: int,
        ship_tickets: int,
        is_delayed: bool = False,
        actions: int = 2,
        current_location: str = "London",
    ):
        self.name = name
        self.health = health
        self.max_health = max_health
        self.sanity = sanity
        self.max_sanity = max_sanity
        self.skills = skills
        self.items = items
        self.clue_tokens = clue_tokens
        self.train_tickets = train_tickets
        self.ship_tickets = ship_tickets
        self.is_delayed = is_delayed
        self.actions = (actions,)
        self.current_location = current_location

    def heal(self, amount: int = 1):
        self.health = min(self.health + amount, self.max_health)
        return self.health

    def restore_sanity(self, amount: int = 1):
        self.sanity = min(self.sanity + amount, self.max_sanity)
        return self.sanity

    def take_damage(self, amount: int = 1):
        self.health = max(self.health - amount, 0)
        return self.health

    def lose_sanity(self, amount: int = 1):
        self.sanity = max(self.sanity - amount, 0)
        return self.sanity

    def gain_clue(self, amount: int = 1):
        self.clue_tokens += amount
        return self.clue_tokens

    def use_clue(self, amount: int = 1):
        if self.clue_tokens >= amount:
            self.clue_tokens -= amount
            return True
        return False

    def add_ticket(self, ticket_type: str, amount: int = 1):
        if ticket_type == "train":
            self.train_tickets += amount
        elif ticket_type == "ship":
            self.ship_tickets += amount
        return self.train_tickets, self.ship_tickets

    def use_ticket(self, ticket_type: str, amount: int = 1):
        if ticket_type == "train":
            if self.train_tickets >= amount:
                self.train_tickets -= amount
                return True
        elif ticket_type == "ship":
            if self.ship_tickets >= amount:
                self.ship_tickets -= amount
                return True
        return False
