from typing import Dict, Any
from game.entities.base.component import EncounterComponent


class ChangeHealthComponent(EncounterComponent):
    def __init__(self, amount: int):
        self.amount = amount

    def process(self, state, investigator, ui=None):
        result = {
            "type": "change_health",
            "amount": self.amount,
        }

        if self.amount > 0:
            final_health = investigator.heal(self.amount)
            result["healed"] = True
        else:
            # Pass the absolute value of the amount to take_damage
            final_health = investigator.take_damage(abs(self.amount))
            result["damaged"] = True

        result["final_health"] = final_health
        result["is_zero"] = final_health <= 0
        return result

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "ChangeHealthComponent":
        """Create a change health component from data dictionary"""
        amount = data.get("amount", 0)
        return cls(amount)
