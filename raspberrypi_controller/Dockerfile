# Stage 1: build the React/Mantine UI.
FROM node:22-slim AS ui
WORKDIR /ui
COPY astromech_server/raspberrypi_controller/ui/package.json astromech_server/raspberrypi_controller/ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY astromech_server/raspberrypi_controller/ui/ ./
RUN npm run build

# Stage 2: the controller service, serving the built UI from ./static.
FROM python:3.12-slim

WORKDIR /app

COPY astromech_server/esp32/sdk/python /app/astromech_boards
RUN pip install --no-cache-dir /app/astromech_boards

COPY astromech_server/raspberrypi_controller/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY astromech_server/raspberrypi_controller/src /app/src
COPY --from=ui /ui/dist /app/src/static

# Names, notes and logs live here: mount a host directory (see bin/run_docker.sh).
ENV DATA_DIR=/data
VOLUME /data
# Firmware images for flashing boards (host dir mounted read-only, see bin/run_docker.sh).
ENV FIRMWARE_DIR=/firmware

WORKDIR /app/src
CMD ["python", "server.py"]
