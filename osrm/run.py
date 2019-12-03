"""
Spawns the OSRM servers and starts an HTTP API for interfacing with them.
"""
import logging

from flask_cors import CORS

from osrm import settings
from osrm.osrmapi import api_factory
from osrm.osrmcontroller import OsrmController, OsrmServerId
from osrm.tasks import contract, restart, init_server, extract


def osrm_initial_contract_chain(server_id: OsrmServerId):
    """
    Return a chain of tasks that need to be
    executed for initial OSRM extract / contract.
    """
    return (
        extract.signature(
            args=(server_id.name,), immutable=True, queue=f"osrm_{server_id.name}_queue"
        )
        | contract.signature(
            args=(server_id.name,), immutable=True, queue=f"osrm_{server_id.name}_queue"
        )
        | restart.signature(
            args=(server_id.name,), immutable=True, queue=f"osrm_{server_id.name}_queue"
        )
    )


def init_parallel(osrm_controller: OsrmController):
    """
    Initialize OSRM server instances in parallel for increased startup speed.
    """

    for server_id in osrm_controller.server_ids:
        chain = init_server.signature(
            args=(server_id.name,), queue=f"osrm_{server_id.name}_queue"
        )

        if settings.OSRM_INITIAL_CONTRACT:
            chain = chain | osrm_initial_contract_chain(server_id)

        chain.delay()


def init_serial(osrm_controller: OsrmController):
    """
    Initialize OSRM server instances in serial/sequential manner, conserving resources.
    """

    chain = None

    for server_id in osrm_controller.server_ids:
        server_init_task = init_server.signature(
            args=(server_id.name,), immutable=True, queue=f"osrm_{server_id.name}_queue"
        )
        if chain is None:
            chain = server_init_task
        else:
            chain = chain | server_init_task

        if settings.OSRM_INITIAL_CONTRACT:
            chain = chain | osrm_initial_contract_chain(server_id)

    if chain is not None:
        chain.delay()


# pylint: disable=invalid-name
# ^ Not all variables are constants!

logging.basicConfig(level=logging.DEBUG)
controller = OsrmController.init_from_data_location(settings.OSRM_DATA_DIR)

app = api_factory(controller)
CORS(app)


def init_controller():
    """
    Initialize the OSRM controller.
    """
    if settings.INIT_PARALLEL:
        init_parallel(controller)
    else:
        init_serial(controller)


def run():
    """
    Initialize the OSRM controller and start the Flask server
    """
    init_controller()
    app.run(host=settings.MANAGER_LISTEN_HOST, port=settings.MANAGER_LISTEN_PORT)


if __name__ == "__main__":
    run()
