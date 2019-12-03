"""
Pytest fixtures
"""
from multiprocessing import Process

import time
import pytest

from osrm.run import app, run


@pytest.fixture
def client():
    """Fixture for Flask testing client."""
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def running_server():
    """Fixture that sets-up the OSRM manager server prior to running any tests."""
    server = Process(target=run)
    server.start()
    print("Waiting for OSRM Manager server to start ...")
    time.sleep(5)
    yield app
    server.terminate()
    server.join()
