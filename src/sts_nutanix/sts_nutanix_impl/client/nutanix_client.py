from logging import Logger
from typing import Any, Dict, List, Union

import requests
from requests.adapters import HTTPAdapter
from requests.structures import CaseInsensitiveDict
from sts_nutanix_impl.model.instance import NutanixSpec
from urllib3.util import Retry


class NutanixClient(object):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"
    V1_KARBON = "v1-karbon"
    V1_ALPHA_KARBON = "v1-alpha-1-karbon"
    V1_BETA_KARBON = "v1-beta-1-karbon"

    def __init__(self, spec: NutanixSpec, log: Logger):
        self.log = log
        self.spec = spec
        self.api_base = {
            self.V1: f"{spec.url}/PrismGateway/services/rest/v1",
            self.V2: f"{spec.url}/PrismGateway/services/rest/v2.0",
            self.V3: f"{spec.prism_central_url}/api/nutanix/v3",
            self.V1_KARBON: f"{spec.prism_central_url}/karbon/v1",
            self.V1_BETA_KARBON: f"{spec.prism_central_url}/karbon/v1-beta.1",
            self.V1_ALPHA_KARBON: f"{spec.prism_central_url}/karbon/v1-alpha.1",
        }

        self._session = self._init_session(spec)

    def post(
        self, api_version: str, uri: str, body: Dict[str, Any] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        body = body or {}
        url = self._get_url(api_version, uri)
        return self._handle_failed_call(self._session.post(url, data=body)).json()

    def get(
        self, api_version: str, uri: str, params: Dict[str, Any] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        url = self._get_url(api_version, uri)
        result = self._handle_failed_call(self._session.get(url, params=params)).json()
        return result

    def get_clusters(self) -> List[Dict[str, Any]]:
        url = self._get_url(self.V2, "clusters")
        return self._get(url).json()["entities"]

    def get_karbon_clusters(self) -> List[Dict[str, Any]]:
        url = self._get_url(self.V1_BETA_KARBON, "k8s/clusters")
        clusters = self._get(url).json()
        for cluster in clusters:
            node_pools = self._get(
                self._get_url(self.V1_ALPHA_KARBON, f"k8s/clusters/{cluster['name']}/node-pools")
            ).json()
            node_pools_lookup = {}
            for node_pool in node_pools:
                node_pools_lookup[node_pool["name"]] = node_pool
            cluster["node_pools"] = node_pools_lookup
        return clusters

    def _post(self, url: str, body: Dict[str, Any] = None) -> requests.Response:
        body = body or {}
        return self._handle_failed_call(self._session.post(url, data=body))

    def _get(self, url: str, params: Dict[str, Any] = None) -> requests.Response:
        return self._handle_failed_call(self._session.get(url, params=params))

    def _get_url(self, api_version: str, uri: str):
        return f"{self.api_base[api_version]}/{uri}"

    @staticmethod
    def _init_session(spec: NutanixSpec) -> requests.Session:
        retry = Retry(
            total=spec.max_request_retries,
            backoff_factor=spec.retry_backoff_seconds,
            status_forcelist=spec.retry_on_status,
        )
        session = requests.Session()
        session.auth = (spec.username, spec.password)
        session.verify = False
        session.headers = CaseInsensitiveDict(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "cache-control": "no-cache",
            }
        )
        session.mount(spec.url, HTTPAdapter(max_retries=retry))
        session.mount(spec.prism_central_url, HTTPAdapter(max_retries=retry))
        return session

    @staticmethod
    def _handle_failed_call(response: requests.Response) -> requests.Response:
        if not response.ok:
            msg = f"Failed to call [{response.url}]. Status code {response.status_code}. {response.text}"
            raise Exception(msg)
        return response
