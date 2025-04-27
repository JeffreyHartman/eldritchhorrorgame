class Investigator:
    def __init__(
        self,
        name,
        health,
        max_health,
        sanity,
        max_sanity,
        skills,
        items,
        clue_tokens,
        tickets,
        is_delayed,
        actions=2,
        current_location="London",
    ):
        self.name = name
        self.health = health
        self.max_health = max_health
        self.sanity = sanity
        self.max_sanity = max_sanity
        self.skills = skills
        self.items = items
        self.clue_tokens = clue_tokens
        self.tickets = tickets
        self.is_delayed = is_delayed
        self.actions = (actions,)
        self.current_location = current_location
