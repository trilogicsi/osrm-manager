## Description

This project spawns OSRM backend servers and provides an HTTP API to control 
and interface with them. 


## Getting started

**Note 1:** Before you can start using OSRM Manager you need to prepare
OSM data. See [Preparing the data](#preparing-the-data) chapter below.

The easiest way to get this project up and running is to use Docker and/or 
docker-compose. The following `docker-compose.yml` example should get you
up and running:

```yaml
version: '3.1'

services:

  osrm-manager:
    image: trilogicsi/osrm-manager
    ports:
      - "127.0.0.1:8088:8000"  # Only needed if you want to access the API from the host
    volumes:
      - ./data:/data
    environment:
      - CELERY_REDIS_HOST=redis
      - CELERY_REDIS_PORT=6799
      - CELERY_REDIS_DB=1   # If you don't have a dedicated Redis DB, you can change the Redis database number
      - OSRM_INITIAL_CONTRACT=false  # Force initial OSRM contract, even if files already exist
      - INIT_PARALLEL=true  # Initialize the OSRM servers in parallel (faster, but uses more resources)
      - OSRM_PREPROCESS_THREADS=4  # Number of threads that each OSRM server uses for data extraction/contraction

  # Redis is required for Celery backend
  redis:
    image: redis:4-alpine
```


## Preparing the data

To get this project up and running, you have to mount the required OSM data in 
the `/data/<osrm_server_name>/` directory (inside the docker container). Each 
directory must contain **exactly one** file with `.osm.pbf` extension (OSM data) 
and **exactly one** `.lua` script (routing profile). OSRM Manager will then 
automatically spawn an OSRM server instance for each such directory (on start-up).

**Example:** If you want to use OSRM Manager for car routing in Slovenia and bicycle 
routing in Austria, create the following directory/file structure:

```
 /data
   |
   ├ Bicycle
   |  ├ bicycle.lua
   |  └ slovenia-latest.osm.pbf
   └ Car
      ├ car.lua
      └ austria-latest.osm.pbf
```  


You can download OpenStreetMap extracts (`.osm.pbf` files) 
from [Geofabrik](http://download.geofabrik.de/) and the routing
profiles from [Project OSRM-backend github page](https://github.com/Project-OSRM/osrm-backend/tree/master/profiles).
 
 
## Running test

The tests run in docker containers and are executed via docker-compose. 
To run the tests do the following:

```shell script
cd tests
docker-compose run --rm test
``` 