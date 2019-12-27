# This Dockefile merges 3 images:
#    1. ProjectOSRM backend (osrm/osrm-backend)
#    2. Official Python3.6 image (python:3.6.8-slim)
#    3. Adds Pipenv + local project

FROM osrm/osrm-backend:v5.22.0
LABEL maintainer="ziga.lesjak@trilogic.si"

# THE FOLLOWING CODE IS COPIED DIRECTLY FROM THE OFFICIAL python:3.6.8-slim Docekerfile:
# https://github.com/docker-library/python/blob/4df129649329186fb42c9c33215b41d82bc0e58e/3.6/stretch/slim/Dockerfile

# ensure local python is preferred over distribution python
ENV PATH /usr/local/bin:$PATH

# http://bugs.python.org/issue19846
# > At the moment, setting "LANG=C" on a Linux system *fundamentally breaks Python 3*, and that's not OK.
ENV LANG C.UTF-8

# runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
		ca-certificates \
		netbase \
	&& rm -rf /var/lib/apt/lists/*

ENV GPG_KEY 0D96DF4D4110E5C43FBFB17F2D347EA6AA65421D
ENV PYTHON_VERSION 3.6.8

RUN set -ex \
	\
	&& savedAptMark="$(apt-mark showmanual)" \
	&& apt-get update && apt-get install -y --no-install-recommends \
		dpkg-dev \
		gcc \
		libbz2-dev \
		libc6-dev \
		libexpat1-dev \
		libffi-dev \
		libgdbm-dev \
		liblzma-dev \
		libncursesw5-dev \
		libreadline-dev \
		libsqlite3-dev \
		libssl-dev \
		make \
		tk-dev \
		wget \
		xz-utils \
		zlib1g-dev \
# as of Stretch, "gpg" is no longer included by default
		$(command -v gpg > /dev/null || echo 'gnupg dirmngr') \
	\
	&& wget -O python.tar.xz "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz" \
	&& wget -O python.tar.xz.asc "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz.asc" \
	&& export GNUPGHOME="$(mktemp -d)" \
	&& ( \
	    gpg --batch --keyserver ha.pool.sks-keyservers.net --recv-keys "$GPG_KEY" \
	    || gpg --batch --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys "$GPG_KEY" \
	    || gpg --batch --keyserver keyserver.ubuntu.com --recv-keys "$GPG_KEY" \
	    || gpg --batch --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys "$GPG_KEY" \
	    || gpg --batch --keyserver pgp.mit.edu --recv-keys "$GPG_KEY" \
	) \
	&& gpg --batch --verify python.tar.xz.asc python.tar.xz \
	&& { command -v gpgconf > /dev/null && gpgconf --kill all || :; } \
	&& rm -rf "$GNUPGHOME" python.tar.xz.asc \
	&& mkdir -p /usr/src/python \
	&& tar -xJC /usr/src/python --strip-components=1 -f python.tar.xz \
	&& rm python.tar.xz \
	\
	&& cd /usr/src/python \
	&& gnuArch="$(dpkg-architecture --query DEB_BUILD_GNU_TYPE)" \
	&& ./configure \
		--build="$gnuArch" \
		--enable-loadable-sqlite-extensions \
		--enable-shared \
		--with-system-expat \
		--with-system-ffi \
		--without-ensurepip \
	&& make -j "$(nproc)" \
	&& make install \
	&& ldconfig \
	\
	&& apt-mark auto '.*' > /dev/null \
	&& apt-mark manual $savedAptMark \
	&& find /usr/local -type f -executable -not \( -name '*tkinter*' \) -exec ldd '{}' ';' \
		| awk '/=>/ { print $(NF-1) }' \
		| sort -u \
		| xargs -r dpkg-query --search \
		| cut -d: -f1 \
		| sort -u \
		| xargs -r apt-mark manual \
	&& apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
	&& rm -rf /var/lib/apt/lists/* \
	\
	&& find /usr/local -depth \
		\( \
			\( -type d -a \( -name test -o -name tests \) \) \
			-o \
			\( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \
		\) -exec rm -rf '{}' + \
	&& rm -rf /usr/src/python \
	\
	&& python3 --version

# make some useful symlinks that are expected to exist
RUN cd /usr/local/bin \
	&& ln -s idle3 idle \
	&& ln -s pydoc3 pydoc \
	&& ln -s python3 python \
	&& ln -s python3-config python-config

# if this is called "PIP_VERSION", pip explodes with "ValueError: invalid truth value '<VERSION>'"
ENV PYTHON_PIP_VERSION 19.1.1

RUN set -ex; \
	\
	savedAptMark="$(apt-mark showmanual)"; \
	apt-get update; \
	apt-get install -y --no-install-recommends wget; \
	\
	wget -O get-pip.py 'https://bootstrap.pypa.io/get-pip.py'; \
	\
	apt-mark auto '.*' > /dev/null; \
	[ -z "$savedAptMark" ] || apt-mark manual $savedAptMark; \
	apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
	rm -rf /var/lib/apt/lists/*; \
	\
	python get-pip.py \
		--disable-pip-version-check \
		--no-cache-dir \
		"pip==$PYTHON_PIP_VERSION" \
	; \
	pip --version; \
	\
	find /usr/local -depth \
		\( \
			\( -type d -a \( -name test -o -name tests \) \) \
			-o \
			\( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \
		\) -exec rm -rf '{}' +; \
	rm -f get-pip.py


# INSTALL LOCAL PACKAGES AND COPY THE PROJECT SOURCES.
# COPIED FROM: deploy/docker/python3.6-stretch/Dockerfile
# build-essentias was added because it is required for building twisted (python lib)

# Note 1: Project root must be specified as build context

RUN apt-get update \
  && apt-get install -y \
    libspatialindex-c4v5 \
    libgdal20 \
    build-essential \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip install pipenv

RUN useradd -m -s /bin/bash osrm-manager \
  && mkdir -p /opt/osrm-manager \
  && chown osrm-manager /opt/osrm-manager -R

USER osrm-manager
WORKDIR /opt/osrm-manager

# Install project requirements
COPY ["Pipfile", "Pipfile.lock", "/opt/osrm-manager/"]

# default argument when not provided in the --build-arg
ARG debug=false

ENV PIPENV_CACHE_DIR=/tmp/pipenv_cache
ENV PIPENV_VENV_IN_PROJECT=1
RUN if [ "$debug" = "false" ]; then \
  (echo "Installing PRODUCTION deps." && pipenv install --deploy); \
  else \
  (echo "Installing DEV deps." && pipenv install --deploy --dev); \
  fi \
  && rm -rf /tmp/pipenv_cache

COPY ["osrm", "/opt/osrm-manager/osrm"]
COPY ["tests", "/opt/osrm-manager/tests"]
COPY ["Pipfile", "Pipfile.lock", "/opt/osrm-manager/"]

ENV PYTHONPATH=/opt/osrm-manager
ENV PATH=/opt/osrm-manager/.venv/bin:${PATH}

EXPOSE 8000
VOLUME ["/data"]
CMD ["pipenv", "run", "python", "osrm/run_gunicorn.py"]
