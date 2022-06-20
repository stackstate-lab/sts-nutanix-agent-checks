import json

from typing import List, Dict, Any

from sts_nutanix_impl.model.instance import InstanceInfo
from sts_nutanix_impl.client.nutanix_client import NutanixClient
from nutanix import NutanixCheck

from stackstate_checks.stubs import topology, health, aggregator
import yaml
import logging
import requests_mock

logging.basicConfig()
logger = logging.getLogger("stackstate_checks.base.checks.base.sl1check")
logger.setLevel(logging.INFO)


@requests_mock.Mocker(kw="m")
def test_check(m: requests_mock.Mocker = None):
    topology.reset()
    instance_dict = setup_test_instance()
    instance = InstanceInfo(instance_dict)
    instance.validate()
    check = NutanixCheck("nutanix", {}, {}, instances=[instance_dict])
    check._init_health_api()

    nutanix = NutanixClient(instance.nutanix, logger)
    print(nutanix.get_url(nutanix.V2, "clusters"))
    m.register_uri("GET", nutanix.get_url(nutanix.V2, "clusters"), json=response("get_clusters_v2"))
    print(nutanix.get_url(nutanix.V1_BETA_KARBON, "k8s/clusters"))
    m.register_uri(
        "GET", nutanix.get_url(nutanix.V1_BETA_KARBON, "k8s/clusters"), json=response("karbon_list_k8s_clusters")
    )
    print(nutanix.get_url(nutanix.V1_ALPHA_KARBON, "k8s/clusters/stackstate/node-pools"))
    m.register_uri(
        "GET",
        nutanix.get_url(nutanix.V1_ALPHA_KARBON, "k8s/clusters/stackstate/node-pools"),
        json=response("karbon_list_cluster_node_pools"),
    )

    print(nutanix.get_url(nutanix.V3, "hosts/list"))
    m.register_uri(
        "POST",
        nutanix.get_url(nutanix.V3, "hosts/list"),
        json=response("list_hosts"),
    )

    print(nutanix.get_url(nutanix.V2, "disks"))
    m.register_uri(
        "GET",
        nutanix.get_url(nutanix.V2, "disks"),
        json=response("get_disks_v2"),
    )

    check.check(instance)
    stream = {"urn": "urn:health:nutanix:nutanix_health", "sub_stream": ""}
    health_snapshot = health._snapshots[json.dumps(stream)]
    health_check_states = health_snapshot["check_states"]
    metric_names = aggregator.metric_names
    snapshot = topology.get_snapshot("")
    components = snapshot["components"]
    relations = snapshot["relations"]
    assert len(components) == 25
    assert len(relations) == 16
    assert len(health_check_states) == 8
    assert len(metric_names) == 4


def response(file_name):
    with open(f"tests/resources/responses/{file_name}.json") as f:
        return json.load(f)


def setup_test_instance() -> Dict[str, Any]:
    with open("tests/resources/conf.d/nutanix.d/conf.yaml.example") as f:
        config = yaml.load(f)
        instance_dict = config["instances"][0]
    return instance_dict


def assert_component(components: List[dict], cid: str) -> Dict[str, Any]:
    component = next(iter(filter(lambda item: (item["id"] == cid), components)), None)
    assert component is not None
    return component


def assert_relation(relations: List[dict], sid: str, tid: str) -> Dict[str, Any]:
    relation = next(
        iter(
            filter(
                # fmt: off
                lambda item: item["source_id"] == sid and item["target_id"] == tid,
                # fmt: on
                relations,
            )
        ),
        None,
    )
    assert relation is not None
    return relation
