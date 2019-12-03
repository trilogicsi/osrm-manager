#!/usr/bin/env bash

# Used to run tests inside docker container; see tests/docker-compose.yml

set -e

echo "Starting OSRM Manager server";
pipenv run python osrm/run.py &

echo "Waiting for OSRM Manager ..."
sleep 5
for i in {1..5}
do
    echo "Waiting for OSRM Manager ..."
    sleep 2
done

echo "Running tests ..."
pipenv run pytest
