# # This Dockefile merges 3 projects into one image:
# #    1. ProjectOSRM backend (osrm/osrm-backend)
# #    2. Official Python image
# #    3. Adds Pipenv + local project


FROM python:3.11.4-bullseye
LABEL maintainer="ziga.lesjak@trilogic.si"

COPY --from=ghcr.io/project-osrm/osrm-backend:v5.27.1 /usr/local /usr/local
COPY --from=ghcr.io/project-osrm/osrm-backend:v5.27.1 /opt /opt

RUN apt-get update && \
    apt-get install -y --no-install-recommends libboost-program-options1.74.0 libboost-regex1.74.0 \
        libboost-date-time1.74.0 libboost-chrono1.74.0 libboost-filesystem1.74.0 \
        libboost-iostreams1.74.0 libboost-system1.74.0 libboost-thread1.74.0 \
        expat liblua5.4-0 && \
    rm -rf /var/lib/apt/lists/* && \
	# add /usr/local/lib to ldconfig to allow loading libraries from there
    ldconfig /usr/local/lib


# INSTALL LOCAL PACKAGES AND COPY THE PROJECT SOURCES.
# COPIED FROM: deploy/docker/python3.6-stretch/Dockerfile
# build-essentias was added because it is required for building twisted (python lib)

# Note 1: Project root must be specified as build context

RUN apt-get update \
  && apt-get install -y \
    libspatialindex-c6 \
    libgdal28 \
    build-essential \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip install pipenv

RUN useradd -m -s /bin/bash osrm-manager \
  && mkdir -p /opt/osrm-manager \
  && chown osrm-manager /opt/osrm-manager -R

USER osrm-manager

COPY Pipfile Pipfile.lock /opt/osrm-manager/
RUN cd /opt/osrm-manager/ \
  && PIPENV_VENV_IN_PROJECT=1 pipenv sync --dev

ENV PATH=/opt/osrm-manager/.venv/bin:${PATH}
