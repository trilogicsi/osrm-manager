#!/usr/bin/env bash

# Used to run tests inside docker container; see tests/docker-compose.yml

set -e

echo "Running tests ..."
pipenv run pytest -x
