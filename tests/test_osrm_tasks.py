"""
Tests for OSRM tasks.
"""
from unittest.mock import patch

from osrm import settings
from osrm.osrmcontroller import OsrmController, OsrmServerId
from osrm.tasks import restart, contract, extract, init_server


@patch("osrm.tasks.OsrmController.restart_osrm_server")
def test_restart(controller_restart):
    """
    Test restart task.
    """
    server_id = OsrmServerId(
        name="Car",
        data="/data/Car/lj-graph-for-tests.osm.pbf",
        profile="'/data/Car/car.lua'",
    )

    controller = OsrmController(
        settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch(
        "osrm.tasks.OsrmController.get_controller_from_redis", lambda: controller
    ):
        restart(server_name=server_id.name)

    controller_restart.assert_called_with(server_id)


@patch("osrm.tasks.OsrmController.contract_osm_data")
def test_contract(controller_contract):
    """
    Test contract task.
    """
    server_id = OsrmServerId(
        name="Car",
        data="/data/Car/lj-graph-for-tests.osm.pbf",
        profile="'/data/Car/car.lua'",
    )

    controller = OsrmController(
        settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch(
        "osrm.tasks.OsrmController.get_controller_from_redis", lambda: controller
    ), patch("osrm.tasks.OsrmController.restore_osrm_data") as restore_osrm_data:
        contract(server_name=server_id.name)

    controller_contract.assert_called_with(server_id, traffic_data=None)
    restore_osrm_data.assert_called_once_with(server_id)


@patch("osrm.tasks.OsrmController.contract_osm_data")
def test_contract_with_traffic(controller_contract):
    """
    Test contract with traffic task.
    """
    server_id = OsrmServerId(
        name="Car",
        data="/data/Car/lj-graph-for-tests.osm.pbf",
        profile="'/data/Car/car.lua'",
    )

    controller = OsrmController(
        settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10000},
        process_ids={server_id: (1, 1.0)},
    )

    traffic_data = "traffic info"

    with patch(
        "osrm.tasks.OsrmController.get_controller_from_redis", lambda: controller
    ), patch("osrm.tasks.OsrmController.restore_osrm_data") as restore_osrm_data:
        contract(server_name=server_id.name, traffic_data=traffic_data)

    controller_contract.assert_called_with(server_id, traffic_data=traffic_data)
    restore_osrm_data.assert_called_once_with(server_id)


@patch("osrm.tasks.OsrmController.extract_osm_data")
def test_extract(controller_extract):
    """
    Test extract task.
    """
    server_id = OsrmServerId(
        name="Car",
        data="/data/Car/lj-graph-for-tests.osm.pbf",
        profile="'/data/Car/car.lua'",
    )

    controller = OsrmController(
        settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch(
        "osrm.tasks.OsrmController.get_controller_from_redis", lambda: controller
    ), patch("osrm.tasks.OsrmController.save_osrm_data") as save_osrm_data:
        extract(server_name=server_id.name)

    controller_extract.assert_called_with(server_id)
    save_osrm_data.assert_called_once_with(server_id)


@patch("osrm.tasks.OsrmController.init_osrm_server")
def test_init_server(controller_init_server):
    """
    Test init server task.
    """
    server_id = OsrmServerId(
        name="Car",
        data="/data/Car/lj-graph-for-tests.osm.pbf",
        profile="'/data/Car/car.lua'",
    )

    controller = OsrmController(
        settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch(
        "osrm.tasks.OsrmController.get_controller_from_redis", lambda: controller
    ):
        init_server(server_name=server_id.name)

    controller_init_server.assert_called_with(server_id)
