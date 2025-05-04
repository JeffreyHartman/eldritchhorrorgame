from typing import List, Dict, Any, Type
from game.entities.base.component import EncounterComponent
from game.entities.investigator import Investigator
import importlib
from game.entities.components.component_factory import create_component


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
        messages = []
        messages.append(f"Test {self.skill} ({self.modifier})")

        # Perform the skill test
        success, rolls = investigator.perform_skill_test(self.skill, self.modifier)

        messages.append(f"Rolls: {rolls}")
        messages.append("Success!" if success else "Failure!")

        # Create result with all necessary information for UI rendering
        result = {
            "type": "skill_test",
            "skill": self.skill,
            "modifier": self.modifier,
            "messages": messages,
            "success": success,
            "rolls": rolls,
        }

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

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "SkillTestComponent":
        """Create a skill test component from data dictionary"""
        skill = data.get("skill")
        modifier = data.get("modifier", 0)

        if skill is None:
            raise ValueError(
                f"Skill test component missing required 'skill' field: {data}"
            )

        # Create success components
        success_components = []
        for success_data in data.get("success_components", []):
            component = create_component(success_data)
            if component:
                success_components.append(component)

        # Create failure components
        failure_components = []
        for failure_data in data.get("failure_components", []):
            component = create_component(failure_data)
            if component:
                failure_components.append(component)

        return cls(skill, modifier, success_components, failure_components)
