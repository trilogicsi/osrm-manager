"""
Tasks consumed by osrm worker.
"""
from typing import Optional

from celery.utils.log import get_task_logger

from osrm.osrm_celery import app
from osrm.osrmcontroller import OsrmController

logger = get_task_logger(__name__)


@app.task(name="osrm.start_server", ignore_result=True)
def init_server(server_name: str):
    """
    Init OSRM server
    :param server_name: name of server to initialize
    """
    osrm_controller = OsrmController.get_controller_from_redis()
    osrm_controller.init_osrm_server(osrm_controller.get_server_id(server_name))


@app.task(name="osrm.contract", ignore_result=True)
def contract(server_name: str, traffic_data: Optional[str] = None):
    """
    Task to contract with traffic data.

    :param traffic_data: Contents of the traffic CSV file (as defined by Project OSRM)
    """
    osrm_controller = OsrmController.get_controller_from_redis()

    server_id = osrm_controller.get_server_id(server_name)

    osrm_controller.restore_osrm_data(server_id)
    osrm_controller.contract_osm_data(server_id, traffic_data=traffic_data)


@app.task(name="osrm.extract", ignore_result=True)
def extract(server_name: str):
    """
    Task to extract OSRM data.
    """
    osrm_controller = OsrmController.get_controller_from_redis()

    server_id = osrm_controller.get_server_id(server_name)
    osrm_controller.extract_osm_data(server_id)
    osrm_controller.save_osrm_data(server_id)


@app.task(name="osrm.restart", ignore_result=True)
def restart(server_name: str):
    """
    Task to restart OSRM server.
    """
    osrm_controller = OsrmController.get_controller_from_redis()

    server_id = osrm_controller.get_server_id(server_name)
    osrm_controller.restart_osrm_server(server_id)


def revoke_all_scheduled_tasks_for_osrm_worker(server_id: "OsrmServerId"):
    """
    Revoke all tasks to contract data
    """
    logger.info("Revoking all scheduled tasks for osrm_%s_worker", server_id.name)

    inspector = app.control.inspect()
    logger.info(inspector.timeout)
    contract_tasks = []

    scheduled_tasks = inspector.scheduled()
    logger.info(scheduled_tasks)

    if scheduled_tasks is None:
        return

    for worker in scheduled_tasks:
        if worker == f"osrm_{server_id.name}_worker":
            contract_tasks = scheduled_tasks[worker]
            break

    for task in contract_tasks:
        task_id = task["request"]["id"]
        app.control.revoke(task_id)

    logger.info("Tasks revoked for osrm_%s_worker", server_id.name)
