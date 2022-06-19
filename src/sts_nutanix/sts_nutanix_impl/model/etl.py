from typing import Any, Dict, List, Set, Union
import itertools

from schematics import Model
from schematics.exceptions import DataError
from schematics.types import ListType, ModelType, StringType, UnionType, DictType
from sts_nutanix_impl.model.stackstate import METRIC_TYPE_CHOICES, EVENT_CATEGORY_CHOICES, AnyType


class DataSource(Model):
    name: str = StringType(required=True)
    module: str = StringType(required=True)
    cls: str = StringType(required=True)
    init: str = StringType(required=True)


class Query(Model):
    name: str = StringType(required=True)
    query: str = StringType(required=True)
    processor: str = StringType(required=False)
    template_refs: List[str] = ListType(StringType(), required=True)


class ComponentTemplateSpec(Model):
    name: str = StringType(required=True)
    component_type: str = StringType(required=True, serialized_name="type")
    uid: str = StringType(required=True)
    layer: str = StringType()
    domain: str = StringType()
    environment: str = StringType()
    labels: Union[str, List[str]] = UnionType((StringType, ListType(StringType)), default=[])
    identifiers: Union[str, List[str]] = UnionType((StringType, ListType(StringType)), default=[])
    relations: Union[str, List[str]] = UnionType((StringType, ListType(StringType)), default=[])
    custom_properties: Union[str, Dict[str, Any]] = UnionType((StringType, DictType(AnyType)), default={})
    processor: str = StringType()


class ComponentTemplate(Model):
    name: str = StringType(required=True)
    selector: str = StringType(default=None)
    spec = ModelType(ComponentTemplateSpec)
    code = StringType()


class EventSourceLink(Model):
    title: str = StringType(required=True)
    url: str = StringType(required=True)


class EventTemplateSpec(Model):
    category: str = StringType(required=True, choices=EVENT_CATEGORY_CHOICES)
    event_type: str = StringType(required=True)
    msg_title: str = StringType(required=True)
    msg_text: str = StringType(required=True)
    element_identifiers: Union[str, List[str]] = UnionType((StringType, ListType(StringType)), default=[])
    source: str = StringType(required=True, default="ETL")
    source_links: List[EventSourceLink] = ListType(ModelType(EventSourceLink, default=[]))
    data: Union[str, Dict[str, Any]] = UnionType((StringType, DictType(AnyType)), default={})
    tags: Union[str, List[str]] = UnionType((StringType, ListType(StringType)), default=[])


class EventTemplate(Model):
    name: str = StringType(required=True)
    selector: str = StringType(default=None)
    spec = ModelType(EventTemplateSpec)


class HealthTemplateSpec(Model):
    check_id: str = StringType(required=True)
    check_name: str = StringType(required=True)
    topo_identifier: str = StringType(required=True)
    message: str = StringType(required=False)
    health: str = StringType(required=True)


class HealthTemplate(Model):
    name: str = StringType(required=True)
    selector: str = StringType(default=None)
    spec = ModelType(HealthTemplateSpec)


class MetricTemplateSpec(Model):
    name: str = StringType(required=True)
    metric_type: str = StringType(required=True)
    value: str = StringType(required=True)
    target_uid: str = StringType(required=True)
    tags: Union[str, List[str]] = UnionType((StringType, ListType(StringType)), default=[])


class MetricTemplate(Model):
    name: str = StringType(required=True)
    selector: str = StringType(default=None)
    spec = ModelType(MetricTemplateSpec)


class ProcessorSpec(Model):
    name: str = StringType(required=True)
    code = StringType()


class Template(Model):
    components: List[ComponentTemplate] = ListType(ModelType(ComponentTemplate), default=[])
    metrics: List[MetricTemplate] = ListType(ModelType(MetricTemplate), default=[])
    events: List[EventTemplate] = ListType(ModelType(EventTemplate), default=[])
    health: List[HealthTemplate] = ListType(ModelType(HealthTemplate), default=[])


class ETL(Model):
    refs: List[str] = ListType(StringType(), default=[])
    processors: List[ProcessorSpec] = ListType(ModelType(ProcessorSpec), default=[])
    datasources: List[DataSource] = ListType(ModelType(DataSource), default=[])
    queries: List[Query] = ListType(ModelType(Query), default=[])
    template: Template = ModelType(Template)
