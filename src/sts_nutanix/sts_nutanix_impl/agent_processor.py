from typing import List

from six import PY3
from stackstate_checks.base import AgentCheck, Health
from sts_nutanix_impl.model.factory import TopologyFactory
from sts_nutanix_impl.model.instance import InstanceInfo
from sts_nutanix_impl.model.stackstate import (Component, HealthCheckState,
                                               Relation)
from sts_nutanix_impl.sync.etl_driver import ETLDriver


class AgentProcessor:
    def __init__(self, instance: InstanceInfo, agent_check: AgentCheck):
        self.agent_check = agent_check
        self.log = agent_check.log
        self.instance = instance
        self.factory = TopologyFactory()

    def process(self):
        self._process_etl()
        self.factory.resolve_relations()
        self._publish()

    def _process_etl(self):
        processor = ETLDriver(self.instance, self.factory, self.agent_check.log)
        processor.process()

    def _publish(self):
        self.log.info(f"Publishing '{len(self.factory.components.values())}' components")
        self.agent_check.start_snapshot()
        components: List[Component] = self.factory.components.values()
        for c in components:
            c.properties.dedup_labels()
            c_as_dict = c.properties.to_primitive()
            self.agent_check.component(self._encode_utf8(c.uid), self._encode_utf8(c.get_type()), c_as_dict)
        self.log.info(f"Publishing '{len(self.factory.relations)}' relations")
        relations: List[Relation] = self.factory.relations.values()
        for r in relations:
            self.agent_check.relation(
                self._encode_utf8(r.source_id),
                self._encode_utf8(r.target_id),
                self._encode_utf8(r.get_type()),
                r.properties,
            )
        self.agent_check.stop_snapshot()
        self._publish_health()
        self._publish_events()
        self._publish_metrics()

    def _publish_health(self):
        self.log.info(f"Synchronizing  '{len(self.factory.health)}' health states")
        health_instances: List[HealthCheckState] = []
        if len(self.factory.health) > 0:
            health_instances = self.factory.health.values()
        self.agent_check.health.start_snapshot()
        deviating, clear, critical = 0, 0, 0
        for health in health_instances:
            health_value = health.health
            if not isinstance(health_value, Health):
                health_value = Health[health_value]
            if health_value == Health.CLEAR:
                clear += 1
            elif health_value == Health.CRITICAL:
                critical += 1
            elif health_value == Health.DEVIATING:
                deviating += 1
            self.agent_check.health.check_state(
                health.check_id,
                health.check_name,
                health_value,
                health.topo_identifier,
                health.message,
            )
        self.log.info(f"Critical -> {critical}, Deviating -> {deviating}, Clear -> {clear}")
        self.agent_check.health.stop_snapshot()

    def _publish_events(self):
        self.log.info(f"Sending  '{len(self.factory.events)}' events")
        for event in self.factory.events:
            event_dict = event.to_primitive(role="public")
            self.agent_check.event(event_dict)

    def _publish_metrics(self):
        self.log.info(f"Sending  '{len(self.factory.metrics)}' metrics")
        for metric in self.factory.metrics:
            metric_func = getattr(self.agent_check, metric.metric_type)
            metric_func(metric.name, metric.value, tags=metric.tags, hostname=metric.target_uid)

    @staticmethod
    def _encode_utf8(string: str) -> str:
        if PY3:
            return string
        else:
            return string.encode("utf-8")
