import json
import logging
import os
import pathlib
from logging import Logger
from typing import Any, Dict, List

import attr
import yaml
from importlib_resources import files
from sts_nutanix_impl.etl.interpreter import (ComponentTemplateInterpreter,
                                              DataSourceInterpreter,
                                              EventTemplateInterpreter,
                                              HeathTemplateInterpreter,
                                              MetricTemplateInterpreter,
                                              ProcessorInterpreter,
                                              QueryInterpreter,
                                              QueryProcessorInterpreter,
                                              TopologyContext)
from sts_nutanix_impl.model.etl import (ETL, ComponentTemplate, EventTemplate,
                                        HealthTemplate, MetricTemplate, Query)
from sts_nutanix_impl.model.factory import TopologyFactory
from sts_nutanix_impl.model.instance import InstanceInfo


class TemplateLookup:
    def __init__(self):
        self.log: Logger = logging.getLogger()
        self.component: Dict[str, ComponentTemplate] = {}
        self.event: Dict[str, EventTemplate] = {}
        self.metric: Dict[str, MetricTemplate] = {}
        self.health: Dict[str, HealthTemplate] = {}

    def index(self, etl: ETL):
        def add(attr_name: str, key: str, value: Any):
            item: Dict[str, Any] = getattr(self, attr_name)
            if key in item:
                logging.error(f"{attr_name} template '{key}' already defined [{etl.source}]."
                              f" Template names must be unique. Ignoring...")
            else:
                item[key] = value

        def add_all(attr_name: str, items: List[Any]):
            for item in items:
                add(attr_name, item.name, item)

        if etl.template is not None:
            add_all("component", etl.template.components)
            add_all("event", etl.template.events)
            add_all("metric", etl.template.metrics)
            add_all("health", etl.template.health)


class ETLDriver:
    def __init__(self, conf: InstanceInfo, factory: TopologyFactory, log: Logger):
        self.log = log
        self.factory = factory
        self.factory.log = log
        self.conf = conf
        conf.etl.source = "conf.yaml"
        self.models = self._init_model(conf.etl)
        self.template_lookup = self._init_template_lookup()

    def process(self):
        global_datasources: Dict[str, Any] = {}
        for model in self.models:
            processor = ETLProcessor(model, self.template_lookup, self.conf, self.factory, self.log)
            ctx = TopologyContext(factory=self.factory, datasources=global_datasources)
            processor.process(ctx)

    def _init_template_lookup(self) -> TemplateLookup:
        lookup = TemplateLookup()
        for model in self.models:
            self.log.info(f"Loading templates from {model.source}.")
            lookup.index(model)
        return lookup

    def _init_model(self, model: ETL) -> List[ETL]:
        model_list: List[ETL] = []
        for etl_ref in model.refs:
            model_list.extend(self._load_ref(etl_ref))
        model_list.append(model)
        return model_list

    def _load_ref(self, etl_ref: str) -> List[ETL]:
        if etl_ref.startswith("module_dir://"):
            yaml_files = sorted(files(etl_ref[13:]).glob("*.yaml"))
        elif etl_ref.startswith("module_file://"):
            yaml_files = [files(etl_ref[14:])]
        elif etl_ref.startswith("file://"):
            file_name = etl_ref[7:]
            if os.path.isfile(file_name):
                yaml_files = [file_name]
            else:
                yaml_files = sorted(pathlib.Path(file_name).glob("*.yaml"))
        else:
            raise Exception(
                f"ETL ref '{etl_ref}' not supported. Must be one of 'module_dir://', 'module_file://'," "'file://'"
            )
        results = []
        for yaml_file in yaml_files:
            with open(str(yaml_file)) as f:
                etl_data = yaml.load(f)
            etl_model = ETL(etl_data["etl"])
            etl_model.source = str(yaml_file)
            etl_model.validate()
            results.extend(self._init_model(etl_model))
        return results


class ETLProcessor:
    def __init__(
        self, etl: ETL, template_lookup: TemplateLookup, conf: InstanceInfo, factory: TopologyFactory, log: Logger
    ):
        self.template_lookup = template_lookup
        self.factory = factory
        self.log = log
        self.conf = conf
        self.etl = etl
        self.query_specs: Dict[str, Query] = {}

    def process(self, ctx: TopologyContext):
        self._process_queries(ctx)
        self._process_post_processors(ctx)

    def _process_queries(self, ctx: TopologyContext):
        counters: Dict[str, int] = {}
        self._init_datasources(ctx)
        for query_spec in self.etl.queries:
            query_results = self._get_query_result(ctx, query_spec)
            if query_results is None or len(query_results) == 0:
                self.log.warning(f"Query {query_spec.name} returned no results! Check query logic in template.")
            counters[f"Query_`{query_spec.name}`_Items"] = len(query_results)
            processed_by_counter = 0
            for template_ref in query_spec.template_refs:
                interpreter = self._get_interpreter(ctx, template_ref)
                for item in query_results:
                    if interpreter.active(item):
                        try:
                            interpreter.interpret(item)
                            processed_by_counter += 1
                        except Exception as e:
                            self.log.error(json.dumps(item, indent=4))
                            raise e
            if processed_by_counter == 0:
                self.log.warning(f"Unprocessed Count for Query {query_spec.name} is 0")
            QueryProcessorInterpreter(ctx).interpret(query_spec)

        self.log.info(f"Query Template Processing Counters:\n{counters}")

    def _get_interpreter(self, ctx, template_ref):
        template = self.template_lookup.component.get(template_ref, None)
        if template:
            return ComponentTemplateInterpreter(ctx, template, self.conf.domain, self.conf.layer, self.conf.environment)
        template = self.template_lookup.event.get(template_ref, None)
        if template:
            return EventTemplateInterpreter(ctx, template, self.conf.domain, self.conf.layer, self.conf.environment)
        template = self.template_lookup.metric.get(template_ref, None)
        if template:
            return MetricTemplateInterpreter(ctx, template, self.conf.domain, self.conf.layer, self.conf.environment)
        template = self.template_lookup.health.get(template_ref, None)
        if template:
            return HeathTemplateInterpreter(ctx, template, self.conf.domain, self.conf.layer, self.conf.environment)
        raise Exception(f"Template '{template_ref}' not found.")

    def _process_post_processors(self, ctx: TopologyContext):
        for processor_spec in self.etl.processors:
            ProcessorInterpreter(ctx).interpret(processor_spec)

    def _init_datasources(self, ctx: TopologyContext):
        interpreter = DataSourceInterpreter(ctx)
        for ds in self.etl.datasources:
            if ds.name not in ctx.datasources:
                interpreter.interpret(ds, self.conf, self.log)

    @staticmethod
    def _get_query_result(ctx: TopologyContext, query: Query) -> List[Dict[str, Any]]:
        interpreter = QueryInterpreter(ctx)
        return interpreter.interpret(query)
