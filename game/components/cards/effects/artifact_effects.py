def glass_of_mortlan_success_manipulation(dice_results, test_type):
    """Each 6 you roll when resolving a Spell effect counts as 2 successes."""
    if test_type == "spell":
        # Count each 6 as 2 successes instead of 1
        extra_successes = dice_results.count(6)
        return extra_successes
    return 0


def glass_of_mortlan_sanity_prevention(game_state, investigator, sanity_loss):
    """You may prevent the loss of 1 Sanity when resolving your Spell effects."""
    if sanity_loss > 0:
        return max(0, sanity_loss - 1)  # Prevent 1 sanity loss
    return sanity_loss


def ttka_halot_action(game_state, investigator, target=None, **kwargs):
    """Test Will. If you pass, spend 1 Sanity to damage monster."""
    test_result = kwargs.get("test_result", {})

    if test_result.get("success", False):
        # If test was successful
        if investigator.spend_sanity(1):
            if target and hasattr(target, "health"):
                target.lose_health(3)
                return True
    return False


# Effect registry
SUCCESS_MANIPULATIONS = {
    "glass_of_mortlan_success": glass_of_mortlan_success_manipulation,
}

PASSIVES = {
    "glass_of_mortlan_sanity": glass_of_mortlan_sanity_prevention,
}

ACTIONS = {
    "ttka_halot_monster_damage": ttka_halot_action,
}

EVENT_TRIGGERS = {
    # Additional event triggers
}
