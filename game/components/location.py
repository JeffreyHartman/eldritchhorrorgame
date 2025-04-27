class Location:
    def __init__(
        self, name, description, connections, has_gate=False, clues=0, monsters=[]
    ):
        self.name = name
        self.description = description
        self.connections = connections
        self.has_gate = has_gate
        self.clues = clues
        self.monsters = monsters
