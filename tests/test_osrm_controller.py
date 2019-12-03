"""
Tests for OsrmController
"""
from unittest.mock import patch

import psutil
import pytest

from osrm import settings

from osrm.osrmcontroller import OsrmServerId, OsrmController

# pylint: disable=invalid-name
server_id = OsrmServerId(
    name="Car",
    data="/data/Car/lj-graph-for-tests.osm.pbf",
    profile="'/data/Car/car.lua'",
)


def test_to_dict():
    """Test to_dict method"""
    controller = OsrmController(
        data_dir=settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10_000},
        process_ids={server_id: (1, 1.0)},
    )

    controller_dict = {
        "data_dir": settings.OSRM_DATA_DIR,
        "server_ids": [server_id],
        "port_bindings": [(server_id, 10_000)],
    }

    assert controller.to_dict() == controller_dict


def test_restart_osrm_server():
    """Test restart_osrm_server method"""
    controller = OsrmController(
        data_dir=settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10_000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch(
        "osrm.osrmcontroller.OsrmController.kill_osrm_server"
    ) as kill_osrm_server:
        with patch(
            "osrm.osrmcontroller.OsrmController.start_osrm_server"
        ) as start_osrm_server:
            controller.restart_osrm_server(server_id)

    kill_osrm_server.asssert_called_with(server_id)
    start_osrm_server.asssert_called_with(server_id)


def test_start_osrm_server():
    """Test start_osrm_server method starts OSRM server"""
    already_running_servers = {
        proc.pid for proc in psutil.process_iter() if proc.cmdline()[0] == "osrm-routed"
    }

    controller = OsrmController(
        data_dir=settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10_000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch(
        "osrm.osrmcontroller.OsrmController.update_server_pid_in_redis"
    ) as update_server_pid_in_redis:
        controller.start_osrm_server(server_id)

    for proc in psutil.process_iter():
        if proc.cmdline():
            if (
                proc.cmdline()[0] == "osrm-routed"
                and proc.pid not in already_running_servers
            ):
                update_server_pid_in_redis.assert_called_with(
                    server_name=server_id.name,
                    server_process_info=(proc.pid, proc.create_time()),
                )
                assert proc.is_running()


def test_kill_osrm_server():
    """
    Test kill_osrm_server method starts OSRM server.
    """
    controller = OsrmController(
        data_dir=settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10_000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch("osrm.osrmcontroller.OsrmController.update_server_pid_in_redis"):
        controller.start_osrm_server(server_id)

    pid = None
    for proc in psutil.process_iter():
        if proc.cmdline():
            if proc.cmdline()[0] == "osrm-routed":
                pid = proc.pid

    assert pid is not None

    with patch("osrm.osrmcontroller.redis.Redis.delete") as delete_key_in_redis:
        controller.kill_osrm_server(server_id)

    delete_key_in_redis.assert_called_with(
        settings.REDIS_SERVER_KEY_TEMPLATE + server_id.name
    )

    with pytest.raises(psutil.NoSuchProcess):
        psutil.Process(pid)


def test_status():
    """
    Test status method.
    """
    controller = OsrmController(
        data_dir=settings.OSRM_DATA_DIR,
        server_ids=[server_id],
        port_bindings={server_id: 10_000},
        process_ids={server_id: (1, 1.0)},
    )

    with patch(
        "osrm.osrmcontroller.OsrmController.get_process_for_server_id",
        lambda _, __: psutil.Process(),
    ):
        with patch("osrm.osrmcontroller.psutil.Process.status", lambda _: "running"):
            status = controller.status()

    assert status == {
        server_id.name: {"port": 10_000, "status": "Running", "busy": True}
    }
