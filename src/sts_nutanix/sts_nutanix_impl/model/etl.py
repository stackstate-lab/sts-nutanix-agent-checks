from typing import Any, Dict, List, Set, Union

from schematics import Model
from schematics.exceptions import DataError
from schematics.types import ListType, ModelType, StringType, UnionType


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
    processor: str = StringType()


class ComponentTemplate(Model):
    name: str = StringType(required=True)
    selector: str = StringType(default=None)
    spec = ModelType(ComponentTemplateSpec)
    code = StringType()


class Template(Model):
    components: List[ComponentTemplate] = ListType(ModelType(ComponentTemplate, default=[]))


class ETL(Model):
    refs: List[str] = ListType(StringType(), default=[])
    datasources: List[DataSource] = ListType(ModelType(DataSource), default=[])
    queries: List[Query] = ListType(ModelType(Query), default=[])
    template: Template = ModelType(Template)

    def validate_refs(self, data: Dict[str, Any], _):
        if not isinstance(data["template"], Template) or not isinstance(data["queries"], list):
            return
        query_refs: Set[str] = set()
        query_names: Set[str] = set()
        template_refs: Set[str] = set()
        for query in data["queries"]:
            query_names.add(query.name)
            for t in query.template_refs:
                template_refs.add(t)

        errors = {}
        template_names = set([t.name for t in data["template"].components])
        if not query_refs.issubset(query_names):
            errors["query_refs_not_found"] = list(query_refs.difference(query_names))

        if not template_refs.issubset(template_names):
            errors["template_refs_not_found"] = list(template_refs.difference(template_names))

        if len(errors.keys()):
            raise DataError(errors)
