"""
Test for OSRM API.
"""
import io
from unittest.mock import patch, call

import hug
import requests
from requests.models import Request

from osrm import settings
from osrm.osrmapi import api_factory
from osrm.osrmcontroller import OsrmController, OsrmServerId

API_ADDRESS = f"http://localhost:{settings.MANAGER_LISTEN_PORT}"

# pylint: disable=invalid-name
server_id = OsrmServerId(
    name="Car",
    data="/data/Car/lj-graph-for-tests.osm.pbf",
    profile="'/data/Car/car.lua'",
)
controller = OsrmController(
    data_dir=settings.OSRM_DATA_DIR,
    server_ids=[server_id],
    port_bindings={server_id: 10_000},
    process_ids={server_id: (1, 1.0)},
)
hug_api = api_factory(controller)


def test_status_api():
    """
    Check status API call works.
    """
    result = requests.get(f"{API_ADDRESS}/status")
    assert result.status_code == 200
    assert result.json() == {
        "Car": {"port": 15000, "status": "Sleeping", "busy": False},
        "Bicycle": {"port": 15001, "status": "Sleeping", "busy": False},
    }


def test_car_osrm_api():
    """
    Test API works as proxy to Car OSRM server
    """
    result = requests.get(
        f"{API_ADDRESS}/osrm/Car/table/v1/wtw/"
        f"14.511150,46.075062;14.479369,46.086541"
        f"?generate_hints=false&annotations=duration,distance"
    ).json()

    assert result["code"] == "Ok"
    assert "destinations" in result
    assert "sources" in result
    assert "destinations" in result
    assert "durations" in result
    assert "distances" in result
    assert result["durations"] == [[0, 148.8], [180.6, 0]]


def test_bicycle_osrm_api():
    """
    Test API works as proxy to Bicycle OSRM server
    """
    result = requests.get(
        f"{API_ADDRESS}/osrm/Bicycle/table/v1/wtw/"
        f"14.511150,46.075062;14.479369,46.086541"
        f"?generate_hints=false&annotations=duration,distance"
    ).json()

    assert result["code"] == "Ok"
    assert "destinations" in result
    assert "sources" in result
    assert "destinations" in result
    assert "durations" in result
    assert "distances" in result
    assert result["durations"] == [[0, 1089.8], [1045.4, 0]]


def test_restart_task():
    """
    Test restart API calls celery restart task.
    """
    # pylint: disable=no-member
    with patch("osrm.osrmapi.restart_task.apply_async") as restart_task:
        result = hug.test.post(hug_api, f"/control/{server_id.name}/restart")

    assert result.status == hug.HTTP_200
    assert result.data == {"success": True}

    restart_task.assert_called_once_with(
        args=(server_id.name,), queue=f"osrm_{server_id.name}_queue"
    )


def test_extract_task():
    """
    Test extract-data API calls celery extract task.
    """
    # pylint: disable=no-member
    with patch("osrm.osrmapi.extract_task.apply_async") as extract_task:
        result = hug.test.post(hug_api, f"/control/{server_id.name}/extract-data")

    assert result.status == hug.HTTP_200
    assert result.data == {"success": True}

    extract_task.assert_called_once_with(
        args=(server_id.name,), queue=f"osrm_{server_id.name}_queue"
    )


def test_contract_task():
    """
    Test contract-data API calls celery contract task.
    """
    # pylint: disable=no-member
    with patch("osrm.osrmapi.contract_task.apply_async") as contract_task, patch(
        "osrm.osrmapi.revoke_all_scheduled_tasks_for_osrm_worker"
    ) as revoke_scheduled_tasks:
        result = hug.test.post(hug_api, f"/control/{server_id.name}/contract-data")

    assert result.status == hug.HTTP_200
    assert result.data == {"success": True, "withTraffic": False}

    revoke_scheduled_tasks.assert_called_once_with(server_id)
    contract_task.assert_called_with(
        args=(server_id.name,), queue=f"osrm_{server_id.name}_queue"
    )


def test_contract_with_traffic_task():
    """
    Test contract-data with traffic API calls celery contract task.
    """
    # pylint: disable=no-member
    # prepare request to mock traffic file upload
    traffic_data = "traffic"
    with io.StringIO(initial_value=traffic_data) as traffic_data_buffer:
        request = Request(
            method="POST",
            url="http://localhost",
            files={"traffic.csv": traffic_data_buffer},
        )
        prepared_request = request.prepare()

    with patch("osrm.osrmapi.contract_task.apply_async") as contract_task, patch(
        "osrm.osrmapi.revoke_all_scheduled_tasks_for_osrm_worker"
    ) as revoke_scheduled_tasks:
        result = hug.test.post(
            hug_api,
            f"/control/{server_id.name}/contract-data",
            headers=prepared_request.headers,
            body=prepared_request.body,
        )

    assert result.status == hug.HTTP_200
    assert result.data == {"success": True, "withTraffic": True}

    revoke_scheduled_tasks.assert_called_once_with(server_id)
    contract_task.assert_has_calls(
        [
            call(
                args=(server_id.name, traffic_data),
                queue=f"osrm_{server_id.name}_queue",
            )
        ]
    )
    assert contract_task.call_count == 2
