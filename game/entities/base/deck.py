import random

class Deck:
    def __init__(self, cards=None, name="Unnamed Deck"):
        self.cards = cards or []
        self.discard_pile = []
        self.name = name
        
    def shuffle(self):
        random.shuffle(self.cards)
        
    def draw(self, n=1):
        if not self.cards and self.discard_pile:
            self.cards = self.discard_pile
            self.discard_pile = []
            self.shuffle()
            
        if not self.cards:
            return []
        
        return self.cards.pop(0)
    
    def discard(self, card):
        self.discard_pile.append(card)
        
    def add_to_top(self, card):
        self.cards.insert(0, card)
        
    def add_to_bottom(self, card):
        self.cards.append(card)