"""
Component factory module for creating components from data.
This provides a central place for component creation logic.
"""

import importlib
from typing import Dict, Any, Optional
from game.entities.base.component import EncounterComponent, CardComponent


def create_component(component_data: Dict[str, Any]) -> Optional[EncounterComponent]:
    """
    Create a component from data dictionary

    Args:
        component_data: Dictionary containing component data with at least a 'type' field

    Returns:
        An instance of the appropriate component class, or None if creation failed
    """
    component_type = component_data.get("type")
    if not component_type:
        raise ValueError(f"Component data missing 'type' field: {component_data}")

    # Dynamically import the component class
    try:
        # Convert snake_case to CamelCase and add "Component"
        class_name = (
            "".join(word.capitalize() for word in component_type.split("_"))
            + "Component"
        )
        module_name = f"game.entities.components.{component_type}"

        module = importlib.import_module(module_name)
        component_class = getattr(module, class_name)

        # Create the component using its from_data method
        return component_class.from_data(component_data)
    except (ImportError, AttributeError) as e:
        print(f"Error creating component of type {component_type}: {str(e)}")
        return None
