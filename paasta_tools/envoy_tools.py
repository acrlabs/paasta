# Copyright 2015-2019 Yelp Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import collections
import socket
from typing import AbstractSet
from typing import Any
from typing import DefaultDict
from typing import Dict
from typing import FrozenSet
from typing import Iterable
from typing import List
from typing import Mapping
from typing import MutableMapping
from typing import Optional
from typing import Sequence
from typing import Set
from typing import Tuple

import requests
from mypy_extensions import TypedDict

from paasta_tools import marathon_tools
from paasta_tools.utils import get_user_agent


class EnvoyBackend(TypedDict, total=False):
    address: str
    port_value: int
    hostname: str
    eds_health_status: str
    weight: int
    has_associated_task: bool


def retrieve_envoy_clusters(
    envoy_host: str, envoy_admin_port: int, envoy_admin_endpoint_format: str
) -> Dict[str, Any]:
    envoy_uri = envoy_admin_endpoint_format.format(
        host=envoy_host, port=envoy_admin_port, endpoint="clusters?format=json"
    )

    # timeout after 1 second and retry 3 times
    envoy_admin_request = requests.Session()
    envoy_admin_request.headers.update({"User-Agent": get_user_agent()})
    envoy_admin_request.mount("http://", requests.adapters.HTTPAdapter(max_retries=3))
    envoy_admin_request.mount("https://", requests.adapters.HTTPAdapter(max_retries=3))
    envoy_admin_response = envoy_admin_request.get(envoy_uri, timeout=1)
    return envoy_admin_response.json()


def get_casper_endpoints(
    clusters_info: Mapping[str, Any]
) -> FrozenSet[Tuple[str, int]]:
    """Filters out and returns casper endpoints from Envoy clusters."""
    casper_endpoints: Set[Tuple[str, int]] = set()
    for cluster_status in clusters_info["cluster_statuses"]:
        if "host_statuses" in cluster_status:
            if cluster_status["name"].startswith("spectre.") and cluster_status[
                "name"
            ].endswith(".egress_cluster"):
                for host_status in cluster_status["host_statuses"]:
                    casper_endpoints.add(
                        (
                            host_status["address"]["socket_address"]["address"],
                            host_status["address"]["socket_address"]["port_value"],
                        )
                    )
    return frozenset(casper_endpoints)


def get_backends(
    service: str,
    envoy_host: str,
    envoy_admin_port: int,
    envoy_admin_endpoint_format: str,
) -> Dict[str, List[Tuple[EnvoyBackend, bool]]]:
    """Fetches JSON from Envoy admin's /clusters endpoint and returns a list of backends.

    :param service: If None, return backends for all services, otherwise only return backends for this particular
                    service.
    :param envoy_host: The host that this check should contact for replication information.
    :param envoy_admin_port: The port that Envoy's admin interface is listening on
    :param envoy_admin_endpoint_format: The format of Envoy's admin endpoint
    :returns backends: A list of dicts representing the backends of all
                       services or the requested service
    """
    if service:
        services = [service]
    else:
        services = None
    return get_multiple_backends(
        services,
        envoy_host=envoy_host,
        envoy_admin_port=envoy_admin_port,
        envoy_admin_endpoint_format=envoy_admin_endpoint_format,
    )


def get_multiple_backends(
    services: Optional[Sequence[str]],
    envoy_host: str,
    envoy_admin_port: int,
    envoy_admin_endpoint_format: str,
) -> Dict[str, List[Tuple[EnvoyBackend, bool]]]:
    """Fetches JSON from Envoy admin's /clusters endpoint and returns a list of backends.

    :param services: If None, return backends for all services, otherwise only return backends for these particular
                     services.
    :param envoy_host: The host that this check should contact for replication information.
    :param envoy_admin_port: The port that Envoy's admin interface is listening on
    :param envoy_admin_endpoint_format: The format of Envoy's admin endpoint
    :returns backends: A list of dicts representing the backends of all
                       services or the requested service
    """
    clusters_info = retrieve_envoy_clusters(
        envoy_host=envoy_host,
        envoy_admin_port=envoy_admin_port,
        envoy_admin_endpoint_format=envoy_admin_endpoint_format,
    )

    casper_endpoints = get_casper_endpoints(clusters_info)

    backends: DefaultDict[
        str, List[Tuple[EnvoyBackend, bool]]
    ] = collections.defaultdict(list)
    for cluster_status in clusters_info["cluster_statuses"]:
        if "host_statuses" in cluster_status:
            if cluster_status["name"].endswith(".egress_cluster"):
                service_name = cluster_status["name"][: -len(".egress_cluster")]

                if services is None or service_name in services:
                    cluster_backends = []
                    casper_endpoint_found = False
                    for host_status in cluster_status["host_statuses"]:
                        address = host_status["address"]["socket_address"]["address"]
                        port_value = host_status["address"]["socket_address"][
                            "port_value"
                        ]

                        # Check if this endpoint is actually a casper backend
                        # If so, omit from the service's list of backends
                        if not service_name.startswith("spectre."):
                            if (address, port_value) in casper_endpoints:
                                casper_endpoint_found = True
                                continue

                        try:
                            hostname = socket.gethostbyaddr(address)[0].split(".")[0]
                        except socket.herror:
                            # Default to the raw IP address if we can't lookup the hostname
                            hostname = address

                        cluster_backends.append(
                            (
                                EnvoyBackend(
                                    address=address,
                                    port_value=port_value,
                                    hostname=hostname,
                                    eds_health_status=host_status["health_status"][
                                        "eds_health_status"
                                    ],
                                    weight=host_status["weight"],
                                ),
                                casper_endpoint_found,
                            )
                        )
                    backends[service_name] += cluster_backends
    return backends


def match_backends_and_tasks(
    backends: Iterable[EnvoyBackend], tasks: Iterable[marathon_tools.MarathonTask]
) -> List[Tuple[Optional[EnvoyBackend], Optional[marathon_tools.MarathonTask]]]:
    """Returns tuples of matching (backend, task) pairs, as matched by IP and port. Each backend will be listed exactly
    once, and each task will be listed once per port. If a backend does not match with a task, (backend, None) will
    be included. If a task's port does not match with any backends, (None, task) will be included.

    :param backends: An iterable of Envoy backend dictionaries, e.g. the list returned by
                     envoy_tools.get_multiple_backends.
    :param tasks: An iterable of MarathonTask objects.
    """

    # { (ip, port) : [backend1, backend2], ... }
    backends_by_ip_port: DefaultDict[
        Tuple[str, int], List[EnvoyBackend]
    ] = collections.defaultdict(list)
    backend_task_pairs = []

    for backend in backends:
        ip = backend["address"]
        port = backend["port_value"]
        backends_by_ip_port[ip, port].append(backend)

    for task in tasks:
        ip = socket.gethostbyname(task.host)
        for port in task.ports:
            for backend in backends_by_ip_port.pop((ip, port), [None]):
                backend_task_pairs.append((backend, task))

    # we've been popping in the above loop, so anything left didn't match a marathon task.
    for backends in backends_by_ip_port.values():
        for backend in backends:
            backend_task_pairs.append((backend, None))

    return backend_task_pairs


def build_envoy_location_dict(
    location: str,
    matched_envoy_backends_and_tasks: Sequence[
        Tuple[Optional[EnvoyBackend], Optional[marathon_tools.MarathonTask]]
    ],
    should_return_individual_backends: bool,
    casper_proxied_backends: AbstractSet[Tuple[str, int]],
) -> MutableMapping[str, Any]:
    running_backends_count = 0
    envoy_backends = []
    is_proxied_through_casper = False
    for backend, task in matched_envoy_backends_and_tasks:
        if backend is None:
            continue
        if backend["eds_health_status"] == "HEALTHY":
            running_backends_count += 1
        if should_return_individual_backends:
            backend["has_associated_task"] = task is not None
            envoy_backends.append(backend)
        if (backend["address"], backend["port_value"]) in casper_proxied_backends:
            is_proxied_through_casper = True
    return {
        "name": location,
        "running_backends_count": running_backends_count,
        "backends": envoy_backends,
        "is_proxied_through_casper": is_proxied_through_casper,
    }


def get_replication_for_all_services(
    envoy_host: str, envoy_admin_port: int, envoy_admin_endpoint_format: str,
) -> Dict[str, int]:
    """Returns the replication level for all services known to this Envoy

    :param envoy_host: The host that this check should contact for replication information.
    :param envoy_admin_port: The port number that this check should contact for replication information.
    :param envoy_admin_endpoint_format: The format of Envoy's admin endpoint
    :returns available_instance_counts: A dictionary mapping the service names
                                        to an integer number of available replicas.
    """
    backends = get_multiple_backends(
        services=None,
        envoy_host=envoy_host,
        envoy_admin_port=envoy_admin_port,
        envoy_admin_endpoint_format=envoy_admin_endpoint_format,
    )
    return collections.Counter(
        [
            service_name
            for service_name, service_backends in backends.items()
            for b in service_backends
            if backend_is_up(b[0])
        ]
    )


def backend_is_up(backend: EnvoyBackend) -> bool:
    return backend["eds_health_status"] == "HEALTHY"
