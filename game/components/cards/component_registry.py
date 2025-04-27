from game.components.cards.card_components import *
from game.components.cards.effects import artifact_effects


def create_component(component_data):
    """Create a component from data"""
    comp_type = component_data.get("type")

    if comp_type == "action":
        action_id = component_data.get("action_id")
        if action_id and action_id in artifact_effects.ACTIONS:
            return ActionComponent(
                name=component_data.get("name", "Unnamed Action"),
                test_type=component_data.get("test_type"),
                test_difficulty=component_data.get("test_difficulty"),
                action_function=artifact_effects.ACTIONS[action_id],
            )

    elif comp_type == "passive":
        effect_id = component_data.get("effect_id")
        if effect_id and effect_id in artifact_effects.PASSIVES:
            return PassiveEffectComponent(
                effect_function=artifact_effects.PASSIVES[effect_id]
            )

    elif comp_type == "test_modifier":
        return TestModifierComponent(
            applies_to_tests=component_data.get("applies_to_tests"),
            additional_dice=component_data.get("additional_dice", 0),
            allows_rerolls=component_data.get("allows_rerolls", False),
            reroll_count=component_data.get("reroll_count", 0),
            success_manipulation=artifact_effects.SUCCESS_MANIPULATIONS.get(
                component_data.get("success_manipulation_id")
            ),
        )

    elif comp_type == "skill_bonus":
        return SkillBonusComponent(
            skill_bonuses=component_data.get("skill_bonuses", {})
        )

    elif comp_type == "event_trigger":
        trigger_id = component_data.get("trigger_id")
        if trigger_id and trigger_id in artifact_effects.EVENT_TRIGGERS:
            return EventTriggerComponent(
                trigger_event=component_data.get("trigger_event"),
                trigger_function=artifact_effects.EVENT_TRIGGERS[trigger_id],
            )

    return None
