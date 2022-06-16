import json
import os
import pathlib
from logging import Logger
from typing import Any, Dict, List

import yaml
from importlib_resources import files
from sts_nutanix_impl.etl.interpreter import (DataSourceInterpreter,
                                              QueryInterpreter,
                                              QueryProcessorInterpreter,
                                              TemplateInterpreter,
                                              TopologyContext)
from sts_nutanix_impl.model.etl import ETL, ComponentTemplate, Query
from sts_nutanix_impl.model.factory import TopologyFactory
from sts_nutanix_impl.model.instance import InstanceInfo


class ETLDriver:
    def __init__(self, conf: InstanceInfo, factory: TopologyFactory, log: Logger):
        self.log = log
        self.factory = factory
        self.factory.log = log
        self.conf = conf
        self.models = self._init_model(conf.etl)

    def process(self):
        global_datasources: Dict[str, Any] = {}
        for model in self.models:
            processor = ETLProcessor(model, self.conf, self.factory, self.log)
            ctx = TopologyContext(factory=self.factory, datasources=global_datasources)
            processor.process(ctx)

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
            etl_model.validate()
            results.extend(self._init_model(etl_model))
        return results


class ETLProcessor:
    def __init__(self, etl: ETL, conf: InstanceInfo, factory: TopologyFactory, log: Logger):
        self.factory = factory
        self.log = log
        self.conf = conf
        self.etl = etl
        self.query_specs: Dict[str, Query] = {}
        self.component_templates: Dict[str, ComponentTemplate] = {}
        self._init_lookup_tables()

    def process(self, ctx: TopologyContext):
        counters: Dict[str, int] = {}
        self._init_datasources(ctx)
        for query_spec in self.etl.queries:
            query_results = self._get_query_result(ctx, query_spec)
            if query_results is None or len(query_results) == 0:
                self.log.warning(f"Query {query_spec.name} returned no results! Check query logic in template.")
            counters[f"Query_`{query_spec.name}`_Items"] = len(query_results)
            unprocessed_items = query_results
            for template_ref in query_spec.template_refs:
                template = self.component_templates[template_ref]
                interpreter = TemplateInterpreter(
                    ctx, template, self.conf.domain, self.conf.layer, self.conf.environment
                )
                still_to_process_devices = []
                for item in unprocessed_items:
                    if interpreter.active(item):
                        try:
                            interpreter.interpret(item)
                        except Exception as e:
                            self.log.error(json.dumps(item, indent=4))
                            raise e
                    else:
                        still_to_process_devices.append(item)
                unprocessed_items = still_to_process_devices
            if len(unprocessed_items) > 0:
                self.log.warning(f"Unprocessed Count for Query {query_spec.name} is {len(unprocessed_items)}")
                self.log.debug([d for d in unprocessed_items])
            QueryProcessorInterpreter(ctx).interpret(query_spec)

        self.log.info(f"Query Template Processing Counters:\n{counters}")

    def _init_lookup_tables(self):
        for qs in self.etl.queries:
            self.query_specs[qs.name] = qs
        if self.etl.template is not None:
            for t in self.etl.template.components:
                self.component_templates[t.name] = t

    def _init_datasources(self, ctx: TopologyContext):
        interpreter = DataSourceInterpreter(ctx)
        for ds in self.etl.datasources:
            if ds.name not in ctx.datasources:
                interpreter.interpret(ds, self.conf, self.log)

    @staticmethod
    def _get_query_result(ctx: TopologyContext, query: Query) -> List[Dict[str, Any]]:
        interpreter = QueryInterpreter(ctx)
        return interpreter.interpret(query)
