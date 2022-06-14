import json

from typing import Dict, Any

from sts_nutanix_impl.client.nutanix_client import NutanixClient
from sts_nutanix_impl.model.instance import InstanceInfo
import yaml
import logging

logging.basicConfig()
logger = logging.getLogger("stackstate_checks.base.checks.base.nutanix")
logger.setLevel(logging.INFO)


def test_connection():
    instance_dict = setup_test_instance()
    instance = InstanceInfo(instance_dict)
    instance.validate()
    client = NutanixClient(instance.nutanix, logger)
    # clusters = client.get_clusters()
    clusters = client.get_karbon_clusters()
    print(json.dumps(clusters, indent=4))


def setup_test_instance() -> Dict[str, Any]:
    with open("tests/resources/conf.d/nutanix.d/conf.yaml.example") as f:
        config = yaml.load(f)
        instance_dict = config["instances"][0]
    return instance_dict
