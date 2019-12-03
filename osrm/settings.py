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
