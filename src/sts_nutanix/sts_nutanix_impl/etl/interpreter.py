import importlib
from logging import Logger
from typing import Any, Dict, List, Optional, Union

import attr
import pydash
from asteval import Interpreter
from jsonpath_ng.exceptions import JsonPathParserError
from six import string_types
from sts_nutanix_impl.model.etl import (ComponentTemplate, DataSource, Query,
                                        Template)
from sts_nutanix_impl.model.factory import TopologyFactory
from sts_nutanix_impl.model.instance import InstanceInfo
from sts_nutanix_impl.model.stackstate import Component


@attr.s(kw_only=True)
class TopologyContext:
    factory: TopologyFactory = attr.ib()
    item: Dict[str, Any] = attr.ib(default=None)
    datasources: Dict[str, Any] = attr.ib(default={})
    component: Component = attr.ib(default=None)

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
        symtable["jpath"] = ctx.jpath
        for name, ds in ctx.datasources.items():
            symtable[name] = ds
        symtable["uid"] = ctx.factory.get_uid
        symtable["py_"] = pydash
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
        conf = self._run_code(datasource.constructor_arg, "constructor_arg")

        try:
            ds_instance = ds_class(conf, log)
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


class TemplateInterpreter(BaseInterpreter):
    def __init__(self, ctx: TopologyContext, template: ComponentTemplate, domain: str, layer: str, environment: str):
        BaseInterpreter.__init__(self, ctx)
        self.environment = environment
        self.layer = layer
        self.domain = domain
        self.template_name = template.name
        self.template = template
        self.source_name = self.template_name

    def active(self, item) -> bool:
        template = self.template
        self.ctx.item = item
        if template.selector is None:
            return True
        return self._get_value(template.selector, "selector")

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

    def _interpret_spec(self, spec: Template) -> Component:
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
        component.uid = self._get_string_property(spec.uid, "uid", None)
        if component.uid is None:
            raise Exception(f"Component uid is required on template" f" `{self.template_name}.")
        self._run_code(spec.processor, "processor")
        component.uid = self._get_string_property(spec.uid, "uid", None)

        component.properties.identifiers.extend(self._merge_list_property(spec.labels, "identifiers"))
        component.properties.identifiers.append(component.uid)
        self.ctx.factory.add_component(component)
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

    def _get_list_property(self, expression: str, name: str, default=None) -> List[Any]:
        if default is None:
            default = []
        values = self._get_value(expression, name, default=default)
        values = self._assert_list(values, name)
        return [self._get_string_property(v, name) for v in values]

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

    def _assert_list(self, value: Any, name: str) -> List[Any]:
        if value is not None:
            if not isinstance(value, list):
                self._raise_assert_error(value, name, "list")
        return value

    def _raise_assert_error(self, value: Any, name: str, expected: str):
        raise AssertionError(
            f"Expected {expected} type for '{name}', but was {type(value)} "
            f"for '{self.source_name}' on `{self.template_name}`"
        )

    def _get_eval_expression_failed_source(self) -> str:
        return f"template '{self.source_name}'"
