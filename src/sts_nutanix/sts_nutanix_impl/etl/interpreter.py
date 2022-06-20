import importlib
from logging import Logger
from typing import Any, Dict, List, Optional, Union

import attr
import pydash
from asteval import Interpreter
from jsonpath_ng.exceptions import JsonPathParserError
from six import string_types
from sts_nutanix_impl.model.etl import (ComponentTemplate,
                                        ComponentTemplateSpec, DataSource,
                                        EventTemplate, EventTemplateSpec,
                                        HealthTemplate, HealthTemplateSpec,
                                        MetricTemplate, MetricTemplateSpec,
                                        ProcessorSpec, Query)
from sts_nutanix_impl.model.factory import TopologyFactory
from sts_nutanix_impl.model.instance import InstanceInfo
from sts_nutanix_impl.model.stackstate import (EVENT_CATEGORY_CHOICES,
                                               HEALTH_STATE_CHOICES,
                                               METRIC_TYPE_CHOICES, Component,
                                               Event, HealthCheckState, Metric,
                                               SourceLink)


@attr.s(kw_only=True)
class TopologyContext:
    factory: TopologyFactory = attr.ib()
    item: Dict[str, Any] = attr.ib(default=None)
    datasources: Dict[str, Any] = attr.ib(default={})
    component: Component = attr.ib(default=None)
    event: Event = attr.ib(default=None)
    metric: Metric = attr.ib(default=None)
    health: HealthCheckState = attr.ib(default=None)

    def jpath(self, path) -> Any:
        return self.factory.jpath(path, self.item)


class BaseInterpreter:
    def __init__(self, ctx: TopologyContext):
        self.ctx = ctx
        self.aeval = Interpreter()
        self.source_name = "default"

    def _run_code(self, code: str, property_name) -> Any:
        if code is None:
            return
        code = code.strip()
        if code.startswith("|"):
            code = code[1:]
        value = self._eval_expression(code, property_name)
        return value

    def _eval_expression(self, expression: str, eval_property: str, fail_on_error: bool = True) -> Any:
        existing_errs = len(self.aeval.error)
        result = self.aeval.eval(expression)
        if len(self.aeval.error) > existing_errs and fail_on_error:
            error_messages = []
            for err in self.aeval.error:
                error_messages.append(err.exc_info)
                error_messages.append(err.get_error())
            raise Exception(
                f"Failed to evaluate property '{eval_property}' on `{self._get_eval_expression_failed_source()}`. "
                f"Expression |\n {expression} \n |.\n Errors:\n {error_messages}"
            )
        return result

    def _get_eval_expression_failed_source(self) -> str:
        return self.source_name

    def _update_asteval_symtable(self) -> Dict[str, Any]:
        symtable = self.aeval.symtable
        ctx = self.ctx
        symtable["factory"] = ctx.factory
        symtable["item"] = ctx.item
        symtable["component"] = ctx.component
        symtable["metric"] = ctx.metric
        symtable["event"] = ctx.event
        symtable["health"] = ctx.health
        symtable["jpath"] = ctx.jpath
        for name, ds in ctx.datasources.items():
            symtable[name] = ds
        symtable["uid"] = ctx.factory.get_uid
        symtable["py_"] = pydash
        symtable["log"] = ctx.factory.log
        return symtable


class DataSourceInterpreter(BaseInterpreter):
    def __init__(self, ctx: TopologyContext):
        BaseInterpreter.__init__(self, ctx)

    def interpret(self, datasource: DataSource, instance_info: InstanceInfo, log: Logger) -> object:
        self.source_name = f"datasource '{datasource.name}'"
        try:
            module = importlib.import_module(datasource.module)
        except Exception as e:
            raise Exception(
                f"Failed to load module '{datasource.module}' for datasource '{datasource.name}'."
                f" Message: {str(e)} "
            )
        try:
            ds_class = getattr(module, datasource.cls)
        except Exception as e:
            raise Exception(
                f"Failed to load class '{datasource.cls}' for datasource '{datasource.name}'." f" Message: {str(e)} "
            )

        symtable = self._update_asteval_symtable()
        symtable["conf"] = instance_info
        symtable[datasource.cls] = ds_class

        try:
            ds_instance = self._run_code(datasource.init, "init")
        except Exception as e:
            raise Exception(
                f"Failed to create class instance '{datasource.cls}' for datasource '{datasource.name}'."
                f" Message: {str(e)} "
            )

        self.ctx.datasources[datasource.name] = ds_instance
        return ds_instance


class QueryInterpreter(BaseInterpreter):
    def __init__(self, ctx: TopologyContext):
        BaseInterpreter.__init__(self, ctx)

    def interpret(self, query: Query) -> List[Dict[str, Any]]:
        self.source_name = f"query '{query.name}'"
        self._update_asteval_symtable()
        items = self._run_code(query.query, "query")
        if items is None:
            items = []
        if not isinstance(items, list):
            items = [items]
        return items


class QueryProcessorInterpreter(BaseInterpreter):
    def __init__(self, ctx: TopologyContext):
        BaseInterpreter.__init__(self, ctx)

    def interpret(self, query: Query):
        self.source_name = f"query '{query.name}'"
        self._update_asteval_symtable()
        self._run_code(query.processor, "processor")


class ProcessorInterpreter(BaseInterpreter):
    def __init__(self, ctx: TopologyContext):
        BaseInterpreter.__init__(self, ctx)

    def interpret(self, processor: ProcessorSpec):
        self.source_name = f"processor '{processor.name}'"
        self._update_asteval_symtable()
        self._run_code(processor.code, "code")


class BaseTemplateInterpreter(BaseInterpreter):
    def __init__(
        self,
        ctx: TopologyContext,
        template: Union[ComponentTemplate, EventTemplate, MetricTemplate, HealthTemplate],
        domain: str,
        layer: str,
        environment: str,
    ):
        BaseInterpreter.__init__(self, ctx)
        self.environment = environment
        self.layer = layer
        self.domain = domain
        self.template_name = template.name
        self.template = template
        self.source_name = self.template_name

    def active(self, item: Any) -> bool:
        template = self.template
        self.ctx.item = item
        if template.selector is None:
            return True
        return self._get_value(template.selector, "selector")

    def _merge_list_property(self, value: Union[Optional[str], List[str]], name: str) -> List[str]:
        if value is None:
            return []
        elif isinstance(value, string_types):
            return self._get_list_property(value, name)
        else:
            return [self._get_string_property(v, name) for v in value]

    def _get_string_property(self, expression: str, name: str, default: str = None) -> str:
        value = self._get_value(expression, name, default=default)
        return self._assert_string(value, name)

    def _get_float_property(self, expression: str, name: str, default: float = 0.0) -> float:
        value = self._get_value(expression, name, default=default)
        return self._assert_float(value, name)

    def _get_list_property(self, expression: Union[str, list], name: str, default=None) -> List[Any]:
        if default is None:
            default = []
        if isinstance(expression, string_types):
            values = self._get_value(expression, name, default=default)
        else:
            values = expression
        values = self._assert_list(values, name)
        return [self._get_string_property(v, name) for v in values]

    def _get_dict_property(self, expression: Union[str, Dict[str, Any]], name: str, default=None) -> Dict[str, Any]:
        if default is None:
            default = {}
        if isinstance(expression, string_types):
            values = self._get_value(expression, name, default=default)
        else:
            values = expression
        values = self._assert_dict(values, name)
        result: Dict[str, Any] = {}
        for k, v in values.items():
            result[k] = self._get_value(v, f"{name}:{k}")
        return result

    def _get_value(self, expression: str, name: str, default: Any = None) -> Any:
        if expression is None:
            return default
        if expression.startswith("$."):
            try:
                return self.ctx.factory.jpath(expression, self.ctx.item, default)
            except JsonPathParserError as e:
                raise Exception(
                    f"Failed to evaluate property '{name}' for '{self.source_name}' on template `{self.template_name}`."
                    f" Expression |\n {expression} \n |.\n Errors:\n {str(e)}"
                )
        elif expression.startswith("|"):
            result = self._run_code(expression, name)
            if result is None:
                return default
            return result
        else:
            return expression

    def _assert_string(self, value: Any, name: str) -> str:
        if value is not None:
            if not isinstance(value, string_types):
                self._raise_assert_error(value, name, "str")
        return value

    def _assert_float(self, value: Any, name: str) -> float:
        if value is not None:
            if isinstance(value, string_types) or isinstance(value, int):
                try:
                    return float(value)
                except Exception:
                    self._raise_assert_error(value, name, "float")
            elif not isinstance(value, float):
                self._raise_assert_error(value, name, "float")
        return value

    def _assert_list(self, value: Any, name: str) -> List[Any]:
        if value is not None:
            if not isinstance(value, list):
                self._raise_assert_error(value, name, "list")
        return value

    def _assert_dict(self, value: Any, name: str) -> Dict[str, Any]:
        if value is not None:
            if not isinstance(value, dict):
                self._raise_assert_error(value, name, "dict")
        return value

    def _raise_assert_error(self, value: Any, name: str, expected: str):
        raise AssertionError(
            f"Expected {expected} type for '{name}', but was {type(value)} "
            f"for '{self.source_name}' on `{self.template_name}`"
        )

    def _get_eval_expression_failed_source(self) -> str:
        return f"template '{self.source_name}'"


class ComponentTemplateInterpreter(BaseTemplateInterpreter):
    def __init__(self, ctx: TopologyContext, template: ComponentTemplate, domain: str, layer: str, environment: str):
        BaseTemplateInterpreter.__init__(self, ctx, template, domain, layer, environment)

    def interpret(self, item: Dict[str, Any]) -> Component:
        template = self.template
        self.ctx.item = item
        self.ctx.component = Component()
        self._update_asteval_symtable()
        if template.spec and template.code:
            raise Exception(f"Template {template.name} cannot have both spec and code properties.")
        if template.spec:
            return self._interpret_spec(template.spec)
        elif template.code:
            return self._interpret_code(template.code)
        else:
            raise Exception(f"Template {template.name} must have either spec and code properties defined.")

    def _interpret_spec(self, spec: ComponentTemplateSpec) -> Component:
        component: Component = self.ctx.component
        component.set_type(self._get_string_property(spec.component_type, "type"))
        component.set_name(self._get_string_property(spec.name, "name"))
        if component.get_name() is None:
            raise Exception(
                f"Component name is required for '{component.get_type()}' on template" f" `{self.template_name}."
            )
        self.source_name = component.get_name()
        component.properties.layer = self._get_string_property(spec.layer, "layer", self.layer)
        component.properties.domain = self._get_string_property(spec.domain, "domain", self.domain)
        component.properties.environment = self._get_string_property(spec.environment, "environment", self.environment)
        component.properties.labels.extend(self._merge_list_property(spec.labels, "labels"))
        component.properties.custom_properties.update(
            self._get_dict_property(spec.custom_properties, "custom_properties")
        )
        component.uid = self._get_string_property(spec.uid, "uid", None)
        if component.uid is None:
            raise Exception(f"Component uid is required on template" f" `{self.template_name}.")
        self._run_code(spec.processor, "processor")
        component.uid = self._get_string_property(spec.uid, "uid", None)

        component.properties.identifiers.extend(self._merge_list_property(spec.labels, "identifiers"))
        component.properties.identifiers.append(component.uid)
        self.ctx.factory.add_component(component)
        self.ctx.factory.add_component_relations(component, self._get_list_property(spec.relations, "relations", []))
        return component

    def _interpret_code(self, code: str) -> Component:
        component = self.ctx.component
        self._run_code(code, "code")
        if component.get_name() is None:
            raise Exception(f"Component name is required for on template `{self.template_name}.")
        if component.properties.layer == "Unknown":
            component.properties.layer = self.layer
        if component.properties.domain == "Unknown":
            component.properties.domain = self.domain
        if component.uid is None:
            raise Exception(f"Component uid is required on template" f" `{self.template_name}.")

        component.properties.identifiers.append(component.uid)
        self.ctx.factory.add_component(component)

        return component


class MetricTemplateInterpreter(BaseTemplateInterpreter):
    def __init__(self, ctx: TopologyContext, template: MetricTemplate, domain: str, layer: str, environment: str):
        BaseTemplateInterpreter.__init__(self, ctx, template, domain, layer, environment)

    def interpret(self, item: Dict[str, Any]) -> Metric:
        template: MetricTemplate = self.template
        self.ctx.item = item
        self.ctx.metric = metric = Metric()
        self._update_asteval_symtable()
        spec: MetricTemplateSpec = template.spec

        metric.name = self._get_string_property(spec.name, "name", None)
        if metric.name is None:
            raise Exception(f"Template {template.name} metric name is required.")

        metric.target_uid = self._get_string_property(spec.target_uid, "target_uid", None)
        metric_type = self._get_string_property(spec.metric_type, "metric_type", "gauge")
        if metric_type not in METRIC_TYPE_CHOICES:
            raise Exception(
                f"Template {template.name} metric type '{metric_type}' not allowed. "
                f"Valid values {METRIC_TYPE_CHOICES}."
            )

        metric.metric_type = metric_type
        metric.value = self._get_float_property(spec.value, "value")
        metric.tags = self._get_list_property(spec.tags, "tags", [])
        self.ctx.factory.add_metric(metric)
        return metric


class EventTemplateInterpreter(BaseTemplateInterpreter):
    def __init__(self, ctx: TopologyContext, template: EventTemplate, domain: str, layer: str, environment: str):
        BaseTemplateInterpreter.__init__(self, ctx, template, domain, layer, environment)

    def interpret(self, item: Dict[str, Any]) -> Event:
        template: EventTemplate = self.template
        self.ctx.item = item
        self.ctx.event = event = Event()
        self._update_asteval_symtable()
        spec: EventTemplateSpec = template.spec

        event.event_type = self._get_string_property(spec.event_type, "event_type", None)
        if event.event_type is None:
            raise Exception(f"Template {template.name} event type is required.")

        category = self._get_string_property(spec.category, "category", "")
        if category not in EVENT_CATEGORY_CHOICES:
            raise Exception(
                f"Template {template.name} event category '{category}' not allowed. "
                f"Valid values {EVENT_CATEGORY_CHOICES}."
            )

        event.context.category = category
        event.context.element_identifiers = self._get_list_property(spec.element_identifiers, "element_identifiers", [])
        event.context.data = self._get_dict_property(spec.data, "data")

        for source_link in spec.source_links:
            sl = SourceLink()
            sl.title = self._get_string_property(source_link.title, "sourcelink.title", None)
            sl.url = self._get_string_property(source_link.url, "sourcelink.url", None)
            event.context.source_links.append(sl)
        event.tags = self._get_list_property(spec.tags, "tags", [])
        source = self._get_string_property(spec.source, "source", "ETL")
        event.context.source = source
        event.source = source
        event.msg_title = self._get_string_property(spec.msg_title, "msg_title", None)
        if event.msg_title is None:
            raise Exception(f"Template {template.name} event msg title is required.")
        event.msg_text = self._get_string_property(spec.msg_text, "msg_text")
        self.ctx.factory.add_event(event)
        return event


class HeathTemplateInterpreter(BaseTemplateInterpreter):
    def __init__(self, ctx: TopologyContext, template: HealthTemplate, domain: str, layer: str, environment: str):
        BaseTemplateInterpreter.__init__(self, ctx, template, domain, layer, environment)

    def interpret(self, item: Dict[str, Any]) -> HealthCheckState:
        template: HealthTemplate = self.template
        self.ctx.item = item
        self.ctx.health = health = HealthCheckState()
        self._update_asteval_symtable()
        spec: HealthTemplateSpec = template.spec

        health.check_id = self._get_string_property(spec.check_id, "check_id", None)
        if health.check_id is None:
            raise Exception(f"Template {template.name} health check id required.")

        health.check_name = self._get_string_property(spec.check_name, "check_name", None)
        if health.check_name is None:
            raise Exception(f"Template {template.name} health check name required.")

        health.topo_identifier = self._get_string_property(spec.topo_identifier, "topo_identifier", None)
        if health.topo_identifier is None:
            raise Exception(f"Template {template.name} health topo_identifier required.")

        health.message = self._get_string_property(spec.message, "message", "")

        health_status = self._get_string_property(spec.health, "health", "")
        if health_status not in HEALTH_STATE_CHOICES:
            raise Exception(
                f"Template {template.name} health '{health_status}' not allowed. "
                f"Valid values {HEALTH_STATE_CHOICES}."
            )

        health.health = health_status
        self.ctx.factory.add_health(health)
        return health
