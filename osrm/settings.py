"""
Settings file for configuring OSRM Manager.
"""

import os
from distutils.util import strtobool  # pylint: disable= no-name-in-module,import-error

OSRM_DATA_DIR = os.environ.get("OSRM_DATA_DIR", "/data")
OSRM_INITIAL_CONTRACT = strtobool(os.environ.get("OSRM_INITIAL_CONTRACT", "true"))

REDIS_CONTROLLER_KEY = "redis-serialized-osrm-controller"
REDIS_SERVER_KEY_TEMPLATE = "redis-serialized-server-pid-"
REDIS_SERVER_PORT_BINDING_TEMPLATE = "redis-serialized-server-port-binding-"

MANAGER_LISTEN_PORT = 8000
MANAGER_LISTEN_HOST = "0.0.0.0"

CELERY_REDIS_HOST = os.environ["CELERY_REDIS_HOST"]
CELERY_REDIS_PORT = int(os.environ.get("CELERY_REDIS_PORT", "6379"))
CELERY_REDIS_DATABASE = int(os.environ.get("CELERY_REDIS_DB", "1"))

INIT_PARALLEL = strtobool(os.environ.get("INIT_PARALLEL", "true"))

OSRM_PREPROCESS_THREADS = int(os.environ.get("OSRM_PREPROCESS_THREADS", "4"))


# OSRM Controller settings

# Maximum number of spawned OSRM servers
CONTROLLER_SERVER_LIMIT = int(
    os.environ.get("CONTROLLER_SERVER_LIMIT", "20")
)
# Spawned server ports will start with this port number
CONTROLLER_SERVER_START_PORT = int(
    os.environ.get("CONTROLLER_SERVER_START_PORT", "15000")
)
# Maximum number of specified locations
CONTROLLER_MAX_DISTANCE_MATRIX_SIZE = int(
    os.environ.get("CONTROLLER_MAX_DISTANCE_MATRIX_SIZE", "200")
)

# Space separated list of addtitional arguments to pass to osrm-routed, eg.: "--algorithm ch --mmap=1"
OSRM_ROUTED_ADDITIONAL_ARGS = os.environ.get("OSRM_ROUTED_ADDITIONAL_ARGS", "").split()