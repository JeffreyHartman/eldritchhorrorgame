class Investigator:
    def __init__(self, name, health, sanity, skills, items, clue_tokens, tickets, is_delayed):
        self.name = name
        self.health = health
        self.max_health = health
        self.sanity = sanity
        self.max_sanity = sanity
        self.skills = skills
        self.items = items
        self.clue_tokens = clue_tokens
        self.tickets = tickets
        self.is_delayed = is_delayed
