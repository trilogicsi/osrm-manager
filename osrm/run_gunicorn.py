"""
Uses gunicorn to spawn OSRM servers and starts
the HTTP API for interfacing with them.

This is production/deployment version of run.py
"""
import multiprocessing

import gevent.monkey

gevent.monkey.patch_all()

# pylint: disable=wrong-import-position
# ^ gevent requires the monkey-patching to occur very early


import gunicorn.app.base

from gunicorn.six import iteritems

from osrm.run import app as flask_app, init_controller
from osrm import settings

MAX_WORKERS = 4

OPTIONS = {
    "bind": f"{settings.MANAGER_LISTEN_HOST}:{settings.MANAGER_LISTEN_PORT}",
    "workers": min([MAX_WORKERS, (multiprocessing.cpu_count() * 2) + 1]),
    "worker_class": "gevent",
    "threads": 1,
    "worker_connections": 1_000,
}


class GunicornApplication(gunicorn.app.base.BaseApplication):
    """
    Class for running a gunicorn server via python code.
    """

    # pylint: disable=abstract-method
    # ^ as per official documentation, we dont need to implement init() in this case

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super(GunicornApplication, self).__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in iteritems(self.options)
            if key in self.cfg.settings and value is not None
        }
        for key, value in iteritems(config):
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


if __name__ == "__main__":
    init_controller()
    GunicornApplication(flask_app, OPTIONS).run()
