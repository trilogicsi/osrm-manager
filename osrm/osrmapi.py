"""
API for controlling OSRM backend servers.
"""
import re

import requests
import requests.adapters
from flask import Flask, request
from urllib3 import Retry
from werkzeug.routing import UnicodeConverter, ValidationError, Rule

from osrm.osrmcontroller import OsrmController
from osrm.tasks import (
    contract as contract_task,
    restart as restart_task,
    revoke_all_scheduled_tasks_for_osrm_worker,
)
from osrm.tasks import extract as extract_task

API_NAME = "OSRM Manager"
OSRM_CONVERTER_NAME = "osrm"


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


def api_factory(osrm_controller: OsrmController) -> Flask:
    """
    Build a Flask API app for the specified OSRM controller instance.
    """
    # pylint: disable=unused-variable
    # ^ flask routes are detected as unused

    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # Limit uploads to 100 MB

    class OsrmServerNameConverter(UnicodeConverter):
        """
        Used to validate OSRM server names
        """

        def to_python(self, value):
            if value not in osrm_controller.server_names:
                raise ValidationError()
            return super().to_python(value)

    app.url_map.converters[OSRM_CONVERTER_NAME] = OsrmServerNameConverter

    @app.route("/", methods=["GET"])
    def index():
        """
        Return the list of available URLs
        """
        url_docs = {}

        for rule in app.url_map.iter_rules():
            rule: Rule
            doc = app.view_functions[rule.endpoint].__doc__
            if any(
                [
                    isinstance(converter, OsrmServerNameConverter)
                    for converter in rule._converters.values()  # pylint: disable=protected-access
                ]
            ):
                doc += "; Valid OSRM server names: " + ", ".join(
                    osrm_controller.server_names
                )

            url_docs[str(rule)] = {
                "allowed_methods": list(rule.methods),
                "doc": format_docstrings(doc),
            }

        return url_docs

    @app.route("/status", methods=["GET"])
    def status():
        """Status of OSRM servers"""
        # need to load controller from Redis as server process IDs could have changed
        # if OSRM server was restarted since creation of API
        recent_osrm_controller = OsrmController.get_controller_from_redis()
        return recent_osrm_controller.status()

    @app.route(
        f"/osrm/<{OSRM_CONVERTER_NAME}:server_name>/<path:osrm_path>", methods=["GET"]
    )
    def osrm_proxy(server_name: str, osrm_path: str):
        """
        Proxy the request to the selected OSRM backend server.
        See ProjectOSRM backend HTTP API documentation for details
        (https://github.com/Project-OSRM/osrm-backend/blob/master/docs/http.md)
        """
        osrm_server_id = osrm_controller.get_server_id(server_name)
        port = osrm_controller.port_bindings[osrm_server_id]

        response = retrying_requests().get(
            f"http://127.0.0.1:{port}/{osrm_path}?{request.query_string.decode()}",
            stream=True,
        )
        return response.raw.read(), response.status_code, response.headers.items()

    @app.route(
        f"/control/<{OSRM_CONVERTER_NAME}:server_name>/restart", methods=["POST"]
    )
    def restart(server_name: str):
        """Restart the selected OSRM server."""
        restart_task.apply_async(args=(server_name,), queue=f"osrm_{server_name}_queue")
        return {"success": True}

    @app.route(
        f"/control/<{OSRM_CONVERTER_NAME}:server_name>/extract-data", methods=["POST"]
    )
    def extract(server_name: str):
        """
        Force an extraction of OSM data. You will almost always
        want to run 'contract-data' after this operation.
        """
        extract_task.apply_async(args=(server_name,), queue=f"osrm_{server_name}_queue")
        return {"success": True}

    @app.route(
        f"/control/<{OSRM_CONVERTER_NAME}:server_name>/contract-data", methods=["POST"]
    )
    def contract_data(server_name: str):
        """
        Force OSRM data contraction. An additional CSV file with traffic
        data can be posted in the request body.

        For CSV file format see:
        https://github.com/Project-OSRM/osrm-backend/wiki/Traffic
        """
        osrm_server_id = osrm_controller.get_server_id(server_name)
        revoke_all_scheduled_tasks_for_osrm_worker(osrm_server_id)

        if not request.files:
            contract_task.apply_async(
                args=(server_name,), queue=f"osrm_{server_name}_queue"
            )
            return {"success": True, "withTraffic": False}

        if len(request.files) != 1 or not next(
            request.files.values()
        ).filename.endswith(".csv"):
            return {
                "success": False,
                "message": f"At most one .csv file must be provided",
            }

        contract_task.apply_async(
            args=(server_name, next(request.files.values()).read().decode()),
            queue=f"osrm_{server_name}_queue",
        )

        update_without_traffic_chain = contract_task.signature(
            countdown=600, args=(server_name,), queue=f"osrm_{server_name}_queue"
        ) | restart_task.signature(
            args=(server_name,), queue=f"osrm_{server_name}_queue", immutable=True
        )

        update_without_traffic_chain.delay()

        return {"success": True, "withTraffic": True}

    return app
