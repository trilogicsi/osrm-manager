"""
API for controlling OSRM backend servers.
"""
import re

import hug
import requests
import requests.adapters
from falcon import HTTP_400  # pylint: disable=no-name-in-module
from urllib3 import Retry

from osrm.osrmcontroller import OsrmController
from osrm.tasks import (
    contract as contract_task,
    restart as restart_task,
    revoke_all_scheduled_tasks_for_osrm_worker,
)
from osrm.tasks import extract as extract_task

API_NAME = "OSRM Manager"


def retrying_requests() -> requests.Session:
    """ Create a Requests session that retries it's requests for about 10 s. """
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.3)  # Max 9.3 seconds of for all retries
    session.mount("http://", requests.adapters.HTTPAdapter(max_retries=retries))
    return session


def format_docstrings(docstring: bytes) -> str:
    """ Fix the formatting of docstrings for a nicer display in API documentation. """
    docstring = str(docstring).replace("\n", "")
    docstring = re.sub(r" +", " ", docstring)
    docstring = re.sub("^ ", "", docstring)
    docstring = re.sub(" $", "", docstring)
    return docstring


def api_factory(osrm_controller: OsrmController) -> hug.API:
    """
    Build a Hug API for the specified OSRM controller instance.
    """
    # pylint: disable=unused-variable
    # ^ hug routes are detected as unused

    router = hug.route.API(API_NAME)

    @router.get("/status")
    def status():
        """Status of OSRM servers."""
        # need to load controller from Redis as server process IDs could have changed
        # if OSRM server was restarted since creation of API
        recent_osrm_controller = OsrmController.get_controller_from_redis()
        return recent_osrm_controller.status()

    @router.get("/osrm/{server_name}/")
    def osrm_proxy(server_name: hug.types.one_of(osrm_controller.server_names)):
        """
        Proxy the request to the selected OSRM backend server.
        See ProjectOSRM backend HTTP API documentation for details
        (https://github.com/Project-OSRM/osrm-backend/blob/master/docs/http.md).
        """
        osrm_server_id = osrm_controller.get_server_id(server_name)
        port = osrm_controller.port_bindings[osrm_server_id]

        response = retrying_requests().get(f"http://127.0.0.1:{port}")
        try:
            return response.json()
        except ValueError:
            return response.content

    @router.sink("/osrm/")
    def osrm_proxy_sink(request, response):
        """
        Proxy the requests to the appropriate OSRM server.
        """
        uri_parts = request.relative_uri.split("/")
        if len(uri_parts) < 3 or uri_parts[2] not in osrm_controller.server_names:
            response.status = HTTP_400
            return {
                "success": False,
                "message": (
                    f"Invalid server name. Must be "
                    f"one of {', '.join(osrm_controller.server_names)}"
                ),
            }

        server_name = uri_parts[2]
        osrm_server_id = osrm_controller.get_server_id(server_name)
        port = osrm_controller.port_bindings[osrm_server_id]
        forward_url = "/".join(uri_parts[3:])

        proxy_response = retrying_requests().get(
            f"http://127.0.0.1:{port}/{forward_url}"
        )

        try:
            json_response = proxy_response.json()
            return json_response
        except ValueError:
            return proxy_response.content

    @router.post("/control/{server_name}/restart")
    def restart(server_name: hug.types.one_of(osrm_controller.server_names)):
        """Restart the selected OSRM server."""
        restart_task.apply_async(args=(server_name,), queue=f"osrm_{server_name}_queue")
        return {"success": True}

    @router.post("/control/{server_name}/extract-data")
    def extract(server_name: hug.types.one_of(osrm_controller.server_names)):
        """
        Force an extraction of OSM data. You will almost always
        want to run 'contract-data' after this operation.
        """
        extract_task.apply_async(args=(server_name,), queue=f"osrm_{server_name}_queue")
        return {"success": True}

    @router.post("/control/{server_name}/contract-data")
    def contract_data(
        body, server_name: hug.types.one_of(osrm_controller.server_names)
    ):
        """
        Force OSRM data contraction. An additional CSV file with traffic
        data can be posted in the request body.

        For CSV file format see:
        https://github.com/Project-OSRM/osrm-backend/wiki/Traffic
        """
        server_id = osrm_controller.get_server_id(server_name)
        osrm_server_id = server_id
        revoke_all_scheduled_tasks_for_osrm_worker(osrm_server_id)

        if body is None:
            contract_task.apply_async(
                args=(server_name,), queue=f"osrm_{server_name}_queue"
            )
            return {"success": True, "withTraffic": False}

        csv_files = {
            filename: content
            for filename, content in body.items()
            if filename.endswith(".csv")
        }
        if len(csv_files) != 1:
            return {
                "success": False,
                "message": f"At most one .csv file must be provided",
            }

        contract_task.apply_async(
            args=(server_name, list(csv_files.values())[0].decode()),
            queue=f"osrm_{server_name}_queue",
        )

        update_without_traffic_chain = contract_task.signature(
            countdown=600, args=(server_name,), queue=f"osrm_{server_name}_queue"
        ) | restart_task.signature(
            args=(server_name,), queue=f"osrm_{server_name}_queue", immutable=True
        )

        update_without_traffic_chain.delay()

        return {"success": True, "withTraffic": True}

    osrm_proxy.__doc__ = format_docstrings(osrm_proxy.__doc__)
    extract.__doc__ = format_docstrings(extract.__doc__)

    return hug.api.API(API_NAME)
