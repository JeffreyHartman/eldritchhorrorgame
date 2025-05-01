"""
Enum definitions for Eldritch Pursuit game.
This module contains all enum classes used throughout the game.
"""

from enum import Enum


class GamePhase(Enum):
    """Game phases enum"""
    ACTION = "Action"
    ENCOUNTER = "Encounter"
    MYTHOS = "Mythos"


class EncounterType(Enum):
    """Encounter types enum"""
    GENERAL = "general"
    AMERICA = "america"
    EUROPE = "europe"
    ASIA = "asia"
    RESEARCH = "research"
    OTHER_WORLD = "other_world"
    EXPEDITION = "expedition"
    SPECIAL = "special"


class EncounterSubType(Enum):
    """Encounter subtypes enum"""
    CITY = "city"
    WILDERNESS = "wilderness"
    SEA = "sea"


class TicketType(Enum):
    """Travel ticket types enum"""
    TRAIN = "train"
    SHIP = "ship"


class AssetType(Enum):
    """Asset types enum"""
    ITEM = "item"
    ALLY = "ally"
    SPELL = "spell"
    ARTIFACT = "artifact"
    CONDITION = "condition"
    CLUE = "clue"
    TRINKET = "trinket"
    TASK = "task"
    SERVICE = "service"


class AssetTrait(Enum):
    """Asset primary trait enum"""
    ITEM = "item"
    TRINKET = "trinket"
    TASK = "task"
    SERVICE = "service"
    ALLY = "ally"


class AssetSecondaryTrait(Enum):
    """Asset secondary trait enum"""
    MAGICAL = "magical"
    RELIC = "relic"
    TOME = "tome"
    WEAPON = "weapon"
    TEAMWORK = "teamwork"
