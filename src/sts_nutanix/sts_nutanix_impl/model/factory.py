from typing import Any, Dict, List, Optional, Union

from jsonpath_ng import parse
from sts_nutanix_impl.model.stackstate import (Component, Event,
                                               HealthCheckState, Relation)
import logging


class TopologyFactory:
    def __init__(self):
        self.components: Dict[str, Component] = {}
        self.relations: Dict[str, Relation] = {}
        self.health: Dict[str, HealthCheckState] = {}
        self.events: List[Event] = []
        self.lookups: Dict[str, Any] = {}
        self.log = logging.getLogger()


    @staticmethod
    def jpath(path: str, target: Any, default: Any = None) -> Union[Optional[Any], List[Any]]:
        jsonpath_expr = parse(path)
        matches = jsonpath_expr.find(target)
        if not matches:
            return default
        if len(matches) == 1:
            return matches[0].value
        return [m.value for m in matches]

    def add_event(self, event: Event):
        self.events.append(event)

    def add_component(self, component: Component):
        if component is None:
            raise Exception("Component cannot be None.")
        component.validate()
        if component.uid in self.components:
            raise Exception(f"Component '{component.uid}' already exists.")
        self.components[component.uid] = component

    def get_component(self, uid: str) -> Component:
        return self.components[uid]

    def get_component_by_name_and_type(
        self, component_type: str, name: str, raise_not_found: bool = True
    ) -> Optional[Component]:
        result = [c for c in self.components.values() if c.component_type == component_type and c.get_name() == name]
        if len(result) == 1:
            return result[0]
        elif len(result) == 0:
            if raise_not_found:
                raise Exception(f"Component ({component_type}, {name}) not found.")
            return None
        else:
            raise Exception(f"More than 1 result found for Component ({component_type}, {name}) search.")

    def get_component_by_name(self, name: str, raise_not_found: bool = True) -> Optional[Component]:
        result = [c for c in self.components.values() if c.get_name() == name]
        if len(result) == 1:
            return result[0]
        elif len(result) == 0:
            if raise_not_found:
                raise Exception(f"Component ({name}) not found.")
            return None
        else:
            raise Exception(f"More than 1 result found for Component ({name}) search.")

    def get_component_by_name_postfix(self, postfix: str) -> Optional[Component]:
        result = [c for c in self.components.values() if c.get_name().endswith(postfix)]
        if len(result) == 1:
            return result[0]
        elif len(result) == 0:
            return None
        else:
            raise Exception(f"More than 1 result found for Component postfix ({postfix}) search.")

    def component_exists(self, uid: str) -> bool:
        return uid in self.components

    def relation_exists(self, source_id: str, target_id: str) -> bool:
        rel_id = f"{source_id} --> {target_id}"
        return rel_id in self.relations

    def add_relation(self, source_id: str, target_id: str, rel_type: str = "uses") -> Relation:
        rel_id = f"{source_id} --> {target_id}"
        if rel_id in self.relations:
            raise Exception(f"Relation '{rel_id}' already exists.")
        relation = Relation({"source_id": source_id, "target_id": target_id, "external_id": rel_id})
        relation.set_type(rel_type)
        self.relations[rel_id] = relation
        return relation

    def add_health(self, health: HealthCheckState):
        if health.check_id in self.health:
            raise Exception(f"Health event '{health.check_id}' already exists.")
        self.health[health.check_id] = health

    @staticmethod
    def get_uid(integration: str, uid_type: str, urn_post_fix: str) -> str:
        sanitize_str = TopologyFactory.sanitize(urn_post_fix)
        return f"urn:{integration}:{uid_type}/{sanitize_str}"

    @staticmethod
    def sanitize(value: str) -> str:
        return value.replace(" ", "_").lower()
