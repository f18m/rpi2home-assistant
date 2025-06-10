# Stage 1: the builder
FROM python:3.11-slim AS builder

# NOTE: git is required to get the "hatch-vcs" plugin to work and produce the _raspy2mqtt_version.py file
RUN apt update && apt install -y git

WORKDIR /build
COPY requirements.txt pyproject.toml README.md /build/
ADD ./src ./src/
COPY ./.git ./.git/

RUN python -m pip install --upgrade pip
RUN pip install --target=/build/deps -r requirements.txt
RUN pip install build
RUN python -m build --wheel --outdir /build/wheel


# Stage 2: Create the final image
FROM python:3.11-slim

LABEL org.opencontainers.image.source=https://github.com/f18m/rpi2home-assistant

# install the wheel
WORKDIR /app
COPY --from=builder /build/wheel/*.whl .
RUN pip3 install --no-cache-dir *.whl

ENV PYTHONUNBUFFERED=1
ENTRYPOINT [ "raspy2mqtt" ]

