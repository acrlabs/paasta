# Stubs for marathon.models.task (Python 3.6)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

from typing import Any, Optional
from .base import MarathonResource as MarathonResource, MarathonObject as MarathonObject

class MarathonTask(MarathonResource):
    DATETIME_FORMAT = ...  # type: str
    app_id = ...  # type: Any
    health_check_results = ...  # type: Any
    host = ...  # type: Any
    id = ...  # type: Any
    ports = ...  # type: Any
    service_ports = ...  # type: Any
    slave_id = ...  # type: Any
    staged_at = ...  # type: Any
    started_at = ...  # type: Any
    state = ...  # type: Any
    version = ...  # type: Any
    ip_addresses = ...  # type: Any
    local_volumes = ...  # type: Any
    def __init__(self, app_id: Optional[Any] = ..., health_check_results: Optional[Any] = ..., host: Optional[Any] = ..., id: Optional[Any] = ..., ports: Optional[Any] = ..., service_ports: Optional[Any] = ..., slave_id: Optional[Any] = ..., staged_at: Optional[Any] = ..., started_at: Optional[Any] = ..., version: Optional[Any] = ..., ip_addresses: Any = ..., state: Optional[Any] = ..., local_volumes: Optional[Any] = ...) -> None: ...

class MarathonIpAddress(MarathonObject):
    ip_address = ...  # type: Any
    protocol = ...  # type: Any
    def __init__(self, ip_address: Optional[Any] = ..., protocol: Optional[Any] = ...) -> None: ...

class MarathonHealthCheckResult(MarathonObject):
    DATETIME_FORMAT = ...  # type: str
    alive = ...  # type: Any
    consecutive_failures = ...  # type: Any
    first_success = ...  # type: Any
    last_failure = ...  # type: Any
    last_success = ...  # type: Any
    task_id = ...  # type: Any
    last_failure_cause = ...  # type: Any
    instance_id = ...  # type: Any
    def __init__(self, alive: Optional[Any] = ..., consecutive_failures: Optional[Any] = ..., first_success: Optional[Any] = ..., last_failure: Optional[Any] = ..., last_success: Optional[Any] = ..., task_id: Optional[Any] = ..., last_failure_cause: Optional[Any] = ..., instance_id: Optional[Any] = ...) -> None: ...
