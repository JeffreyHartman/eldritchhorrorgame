from typing import List, Dict, Any
from game.entities.base.component import EncounterComponent
from game.entities.investigator import Investigator


class SkillTestComponent(EncounterComponent):
    def __init__(
        self,
        skill: str,
        modifier: int,
        success_components: List[EncounterComponent],
        failure_components: List[EncounterComponent],
    ):
        self.skill = skill
        self.modifier = modifier
        self.success_components = success_components
        self.failure_components = failure_components

    def process(self, state, investigator: Investigator, ui=None) -> Dict[str, Any]:
        # Create result with all necessary information for UI rendering
        result = {
            "type": "skill_test",
            "skill": self.skill,
            "modifier": self.modifier,
            "messages": [f"Test {self.skill} ({self.modifier})"]
        }
        
        # Perform the skill test
        success, rolls = investigator.perform_skill_test(self.skill, self.modifier)
        
        # Add results to the result dictionary
        result["success"] = success
        result["rolls"] = rolls
        result["messages"].append(f"Rolls: {rolls}")
        result["messages"].append("Success!" if success else "Failure!")
        
        # Process appropriate components based on success/failure
        component_results = []
        if success:
            for component in self.success_components:
                component_result = component.process(state, investigator, ui)
                component_results.append(component_result)
            result["component_results"] = component_results
        else:
            for component in self.failure_components:
                component_result = component.process(state, investigator, ui)
                component_results.append(component_result)
            result["component_results"] = component_results
        
        return result
