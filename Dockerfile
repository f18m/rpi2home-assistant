# Stage 1: the builder
FROM python:3.11-slim AS builder

WORKDIR /app
RUN mkdir /app/raspy2mqtt
ADD raspy2mqtt /app/raspy2mqtt
COPY pyproject.toml README.md /app
RUN ls -l /app
RUN pip3 install build

# produce the wheel
RUN python3 -m build


# Stage 2: Create the final image
FROM python:3.11-slim

# install the wheel
WORKDIR /app
COPY --from=builder /app/dist/*.whl .
RUN pip3 install --no-cache-dir *.whl

CMD [ "raspy2mqtt", "-c", "/app/config.yaml"]
