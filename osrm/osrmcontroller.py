"""
Controlling of OSRM servers (spawning servers,
extracting OSM data, importing traffic, etc.).
"""
# pylint: disable=logging-format-interpolation
import json
import logging
import os
import shutil
import signal
import tempfile
from multiprocessing import Process
from subprocess import Popen, check_call, TimeoutExpired
from typing import List, NamedTuple, Dict, Tuple, Any, Optional

import psutil
import redis

from osrm import settings
from osrm.osrm_celery import app

logger = logging.getLogger(__name__)


class OsrmServerId(NamedTuple):
    """
    Each instance of OSRM backend server is uniquely identified by
    the contents of this tuple.
    """

    name: str
    data: str
    profile: str

    @property
    def osrm_file(self):
        """Return the filename of the extracted `.osrm` file."""
        return self.data_base_name + ".osrm"

    @property
    def data_base_name(self):
        """Return the root of the data file name (ie. stripped of extension)."""
        if not self.data.endswith(OsrmController.MAP_DATA_FILE_EXT):
            raise ValueError("Unknown format of data name.")
        return self.data[: -len(OsrmController.MAP_DATA_FILE_EXT)]

    def get_file_abs_path(self, filename: str, data_dir: str):
        """
        Return the absolute full file path of the specified filename.
        """
        return os.path.join(data_dir, self.name, filename)


class OsrmServerBusyError(Exception):
    """
    Raised if the user tried to perform an action on an instance of OSRM
    server that is currently preforming another task (ie. restarting).
    """


class OsrmController:
    """
    Class for controlling OSRM servers.
    """

    # pylint: disable=too-many-public-methods

    MAP_DATA_FILE_EXT = ".osm.pbf"
    PROFILE_SCRIPT_EXT = ".lua"

    # Maximum duration of any single OSM data pre-processing
    # operation (set to None to disable timeout)
    PROCESS_TIMEOUT: Optional[int] = None
    # Number of seconds the server has to run before it's considered online
    SERVER_STARTUP_TIME = 2
    # Number of seconds to wait for serve to stop before killing it
    SERVER_SHUTDOWN_TIME = 5

    # Maximum number of spawned OSRM servers
    SERVER_LIMIT = settings.CONTROLLER_SERVER_LIMIT
    # Spawned server ports will start with this port number
    SERVER_START_PORT = settings.CONTROLLER_SERVER_START_PORT
    # Maximum number of specified locations
    MAX_DISTANCE_MATRIX_SIZE = settings.CONTROLLER_MAX_DISTANCE_MATRIX_SIZE

    EXTRACT_SAVE_DIR = "extract-saved"

    # File extensions that have to be present in order to consider the extraction done
    EXTRACTED_EXT = [
        ".osrm.cnbg",
        ".osrm.cnbg_to_ebg",
        ".osrm.ebg",
        ".osrm.ebg_nodes",
        ".osrm.edges",
        ".osrm.enw",
        ".osrm.fileIndex",
        ".osrm.geometry",
        ".osrm.icd",
        ".osrm.maneuver_overrides",
        ".osrm.names",
        ".osrm.nbg_nodes",
        ".osrm.properties",
        ".osrm.ramIndex",
        ".osrm.restrictions",
        ".osrm.timestamp",
        ".osrm.tld",
        ".osrm.tls",
        ".osrm.turn_duration_penalties",
        ".osrm.turn_penalties_index",
        ".osrm.turn_weight_penalties",
    ]

    # File extensions that have to be present in order to consider the contraction done
    CONTRACT_EXT = [".osrm.datasource_names", ".osrm.hsgr"]

    _redis_instance = redis.Redis(
        host=settings.CELERY_REDIS_HOST,
        port=settings.CELERY_REDIS_PORT,
        db=settings.CELERY_REDIS_DATABASE,
        decode_responses=True,
    )

    def __init__(
        self,
        data_dir,
        server_ids: List[OsrmServerId],
        port_bindings: Dict[OsrmServerId, int],
        process_ids: Dict[OsrmServerId, Tuple[int, float]],
    ):
        self.data_dir = data_dir
        self.server_ids = server_ids

        if len(self.server_ids) > self.SERVER_LIMIT:
            raise RuntimeError(
                f"Maximum number of servers exceeded "
                f"({len(self.server_ids)}/{self.SERVER_LIMIT})"
            )

        self.port_bindings = port_bindings

        if not self.server_ids:
            raise RuntimeError("No server IDs provided.")

        self.process_ids = process_ids

    @classmethod
    def init_from_data_location(cls, data_dir: str):
        """
        Initialize OsrmController from data directory.
        :param data_dir: path to OSRM data directory
        :return: instance of OsrmController
        """
        server_ids = cls.get_data_files(data_dir)

        if len(server_ids) > cls.SERVER_LIMIT:
            raise RuntimeError(
                f"Maximum number of servers exceeded "
                f"({len(server_ids)}/{cls.SERVER_LIMIT})"
            )

        port_bindings = dict(
            zip(
                server_ids,
                range(cls.SERVER_START_PORT, cls.SERVER_START_PORT + cls.SERVER_LIMIT),
            )
        )

        if not server_ids:
            raise RuntimeError("No data files found. Cannot spawn any OSRM servers.")

        process_ids = dict()
        controller = cls(
            data_dir=data_dir,
            server_ids=server_ids,
            port_bindings=port_bindings,
            process_ids=process_ids,
        )
        controller.init_workers()

        return controller

    def init_workers(self):
        """
        Start OSRM servers and Celery workers.
        """
        # create worker and queue for each server
        for server_id in self.server_ids:
            Process(
                target=self.create_osrm_worker, args=(server_id,), daemon=True
            ).start()
        self.save_controller_in_redis()

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns dictionary of values for serialization.
        """
        serialized_dict = {
            "data_dir": self.data_dir,
            "port_bindings": list(self.port_bindings.items()),
            "server_ids": self.server_ids,
        }

        return serialized_dict

    @classmethod
    def get_controller_from_redis(cls) -> "OsrmController":
        """
        Get osrm controller from Redis.
        """

        data_dict = json.loads(cls._redis_instance.get(settings.REDIS_CONTROLLER_KEY))

        server_ids = [OsrmServerId(*server_id) for server_id in data_dict["server_ids"]]

        port_bindings = {
            OsrmServerId(*server_id): port
            for server_id, port in data_dict["port_bindings"]
        }

        process_ids = {
            server_id: cls.get_server_pid_in_redis(server_id.name)
            for server_id in server_ids
            if cls.get_server_pid_in_redis(server_id.name) is not None
        }

        return cls(
            data_dir=data_dict["data_dir"],
            server_ids=server_ids,
            process_ids=process_ids,
            port_bindings=port_bindings,
        )

    def save_controller_in_redis(self):
        """
        Write controller to redis.
        """
        self._redis_instance.set(
            settings.REDIS_CONTROLLER_KEY, json.dumps(self.to_dict())
        )

    @classmethod
    def update_server_pid_in_redis(
        cls, server_name: str, server_process_info: Tuple[int, float]
    ):
        """
        Update PID and created_time for server key in Redis.
        :param server_name: name of server
        :param server_process_info: unique identifier for process (pid + creation time)
        """
        cls._redis_instance.set(
            settings.REDIS_SERVER_KEY_TEMPLATE + server_name,
            json.dumps(server_process_info),
        )

    @classmethod
    def get_server_pid_in_redis(cls, server_name: str) -> Optional[Tuple[int, float]]:
        """
        Get PID and created_time for server name in Redis.
        :param server_name: name of server
        """
        pid_from_redis = cls._redis_instance.get(
            settings.REDIS_SERVER_KEY_TEMPLATE + server_name
        )

        if pid_from_redis is None:
            return None

        return tuple(json.loads(pid_from_redis))

    @staticmethod
    def create_osrm_worker(server_id: OsrmServerId):
        """
        Creates one celery worker and queue for specific osrm server.
        :param server_id: id of osrm server
        """
        app.worker_main(
            [
                "worker",
                "--loglevel=INFO",
                f"--queues=osrm_{server_id.name}_queue",
                "--concurrency=1",
                f"--hostname=osrm_{server_id.name}_worker",
            ]
        )

    @property
    def server_names(self) -> List[str]:
        """Return the name of all the loaded/spawned servers."""
        return [server_id.name for server_id in self.server_ids]

    def get_process_for_server_id(self, server_id: OsrmServerId) -> psutil.Process:
        """
        Get psutils Process for served ID.

        :param server_id: ID of OSRM server
        :return: process for OSRM server
        """
        pid, start_time = self.process_ids[server_id]

        process = psutil.Process(pid)

        if process.create_time() == start_time:
            return process

        raise ValueError(f"Server process with PID {pid} does not exist")

    def status(self) -> dict:
        """
        Return a dict with OSRM server names
        and their statuses (running/not-running).
        """
        statuses = dict()
        for server_id, _ in self.process_ids.items():
            process = self.get_process_for_server_id(server_id)
            statuses[server_id.name] = {
                "port": self.port_bindings[server_id],
                "status": process.status().capitalize(),
                "busy": process.status() == psutil.STATUS_RUNNING,
            }
        return statuses

    def get_server_id(self, server_name) -> OsrmServerId:
        """Get the OsrmServerId tuple from a server name."""
        for server_id in self.server_ids:
            if server_id.name == server_name:
                return server_id
        raise ValueError(f"ServerID with name '{server_name}' does not exist.")

    def start_osrm_server(self, server_id: OsrmServerId) -> None:
        """
        Spawn an instance of OSRM server.
        """
        port = self.port_bindings[server_id]
        logger.info(f"Starting OSRM server for {server_id.name} on port {port}")

        args = [
            "osrm-routed",
            "-p",
            f"{port:d}",
            "--max-table-size",
            f"{self.MAX_DISTANCE_MATRIX_SIZE:d}",
        ]

        if (
            "--algorithm" not in settings.OSRM_ROUTED_ADDITIONAL_ARGS
            and "-a" not in settings.OSRM_ROUTED_ADDITIONAL_ARGS
        ):
            args += ["--algorithm", "ch"]

        args += settings.OSRM_ROUTED_ADDITIONAL_ARGS + [
            server_id.get_file_abs_path(server_id.osrm_file, self.data_dir)
        ]

        process = Popen(
            args,
            universal_newlines=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=self.SERVER_STARTUP_TIME)
            raise RuntimeError(
                f"OSRM Server {server_id.name} failed to start:\n"
                f"STDOUT: {stdout}"
                f"STDERR: {stderr}"
            )
        except TimeoutExpired:
            pass

        logger.info(
            f"OSRM server for {server_id.name} started "
            f"(up for {self.SERVER_STARTUP_TIME}s). "
            f"Maximum table size: {self.MAX_DISTANCE_MATRIX_SIZE}"
        )

        proces_info = (process.pid, psutil.Process(process.pid).create_time())

        self.process_ids[server_id] = proces_info
        self.update_server_pid_in_redis(
            server_name=server_id.name, server_process_info=proces_info
        )

    def kill_osrm_server(self, server_id: OsrmServerId) -> None:
        """
        Kill an instance of OSRM server, if running.
        """
        logger.info(f"Trying to stop OSRM server {server_id.name}")
        try:
            process = self.get_process_for_server_id(server_id)
        except psutil.NoSuchProcess:
            return

        if process.status() == psutil.STATUS_STOPPED:
            # Process already stopped
            return

        process.send_signal(signal.SIGINT)

        # wait for processes to finish
        _, alive = psutil.wait_procs([process], timeout=self.SERVER_SHUTDOWN_TIME)

        for proc in alive:
            proc.kill()

        self.process_ids.pop(server_id)
        self._redis_instance.delete(settings.REDIS_SERVER_KEY_TEMPLATE + server_id.name)

        try:
            if (
                process.status() != psutil.STATUS_STOPPED
                and process.status() != psutil.STATUS_ZOMBIE
            ):
                raise RuntimeError(f"Could not kill OSRM server {server_id.name}")
        except psutil.NoSuchProcess:
            pass

    def restart_osrm_server(self, server_id: OsrmServerId) -> None:
        """
        Restart an instance of OSRM server.
        """
        self.kill_osrm_server(server_id)
        self.start_osrm_server(server_id)

    def init_osrm_server(self, server_id: OsrmServerId) -> None:
        """
        Spawn a OSRM server instance for the specified server_id. Pre-computes
        the required data, if missing.
        """
        if self.extract_required(server_id):
            self.extract_osm_data(server_id)

        if self.contract_required(server_id):
            self.contract_osm_data(server_id)

        self.start_osrm_server(server_id)

    def extract_osm_data(self, server_id: OsrmServerId) -> None:
        """
        Extract the required data from the
        """
        logger.info(f"Recomputing OSM data for {server_id.name}")
        check_call(
            [
                "osrm-extract",
                "--threads",
                f"{settings.OSRM_PREPROCESS_THREADS:d}",
                "-p",
                server_id.get_file_abs_path(server_id.profile, self.data_dir),
                server_id.get_file_abs_path(server_id.data, self.data_dir),
            ],
            timeout=self.PROCESS_TIMEOUT,
        )

    def save_osrm_data(self, server_id: OsrmServerId) -> None:
        """
        Save .osrm file in separate file, available for restore later.
        """

        if self.extract_required(server_id):
            raise ValueError(f"Extract must be called before saving OSRM data.")

        save_dir_path = server_id.get_file_abs_path(
            self.EXTRACT_SAVE_DIR, self.data_dir
        )

        if not os.path.exists(save_dir_path):
            os.mkdir(save_dir_path)

        for ext in self.EXTRACTED_EXT:
            shutil.copyfile(
                src=server_id.get_file_abs_path(
                    f"{server_id.data_base_name}{ext}", self.data_dir
                ),
                dst=os.path.join(save_dir_path, f"{server_id.data_base_name}{ext}"),
            )

    def restore_osrm_data(self, server_id: OsrmServerId) -> None:
        """
        Restore saved .osrm file.
        """
        restore_dir_path = server_id.get_file_abs_path(
            self.EXTRACT_SAVE_DIR, self.data_dir
        )

        if not os.path.isdir(restore_dir_path):
            raise ValueError(
                f"Directory '{restore_dir_path}' doesn't exist. "
                f"Perhaps save_osrm_data wasn't called?"
            )

        for ext in self.EXTRACTED_EXT:
            shutil.copyfile(
                src=os.path.join(restore_dir_path, f"{server_id.data_base_name}{ext}"),
                dst=server_id.get_file_abs_path(
                    f"{server_id.data_base_name}{ext}", self.data_dir
                ),
            )

    def contract_osm_data(self, server_id: OsrmServerId, traffic_data=None) -> None:
        """
        Prepare OSM data for contraction hierarchies. Optionally take into account
        the traffic data (if available and not ignored).
        """

        logger.info(f"Contracting OSM data for {server_id.name}")

        if traffic_data is None:
            check_call(
                [
                    "osrm-contract",
                    "--threads",
                    f"{settings.OSRM_PREPROCESS_THREADS:d}",
                    server_id.get_file_abs_path(server_id.osrm_file, self.data_dir),
                ],
                timeout=self.PROCESS_TIMEOUT,
            )
        else:
            with tempfile.NamedTemporaryFile(mode="w") as csv_file:
                csv_file.write(traffic_data)
                check_call(
                    [
                        "osrm-contract",
                        "--threads",
                        f"{settings.OSRM_PREPROCESS_THREADS:d}",
                        server_id.get_file_abs_path(server_id.osrm_file, self.data_dir),
                        "--segment-speed-file",
                        csv_file.name,
                    ],
                    timeout=self.PROCESS_TIMEOUT,
                )

        logger.info(f"Contracting finished for {server_id.name}")

    def extract_required(self, server_id: OsrmServerId) -> bool:
        """
        Check if the required data has already been extracted for
        the specified OSRM server instance.
        """
        for ext in self.EXTRACTED_EXT:
            file = server_id.get_file_abs_path(
                server_id.data_base_name + ext, self.data_dir
            )
            if not os.path.isfile(file):
                break
        else:
            return False

        return True

    def contract_required(self, server_id: OsrmServerId) -> bool:
        """
        Check if the required data has already been contracted
        for the specified OSRM server instance.

        TODO: take into account old/outdated traffic?
        """
        for ext in self.CONTRACT_EXT:
            file = server_id.get_file_abs_path(
                server_id.data_base_name + ext, self.data_dir
            )
            if not os.path.isfile(file):
                break
        else:
            return False

        return True

    @classmethod
    def get_data_files(cls, data_dir) -> List[OsrmServerId]:
        """
        Scan the data folder, validate it and
        return the list of available vehicle types.
        """
        vehicle_type_data_files = []

        for dirpath, _, filenames in os.walk(data_dir):
            if os.path.abspath(os.path.dirname(dirpath)) != os.path.abspath(data_dir):
                continue

            current_path = os.path.abspath(dirpath)
            server_name = os.path.split(current_path)[1]

            data_files = [
                file.strip()
                for file in filenames
                if file.strip().endswith(cls.MAP_DATA_FILE_EXT)
            ]
            profile_files = [
                file.strip()
                for file in filenames
                if file.strip().endswith(cls.PROFILE_SCRIPT_EXT)
            ]

            if len(data_files) > 1 or len(profile_files) > 1:
                logger.error(
                    f"Ignoring '{current_path}'. Multiple data/profile/traffic files "
                    f"found (there should be only 1 of each per directory). "
                    f"Data files found: {', '.join(data_files)}; "
                    f"Profile files found: {', '.join(profile_files)}; "
                )
            elif data_files and profile_files:
                logger.info(f"Detected data directory: '{current_path}'")
                vehicle_type_data_files.append(
                    OsrmServerId(server_name, data_files[0], profile_files[0])
                )

        return vehicle_type_data_files
