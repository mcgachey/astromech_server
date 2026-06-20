# astromech_server

HTTP server that exposes Galaxy's Edge astromech droid control via REST API. Bridges Home Assistant with physical droids over Bluetooth using `libastromech`.

## Prerequisites

- Raspberry Pi with Docker installed
- Bluetooth adapter (built-in on Pi 3/4/5)

## Configuration

Create a `droids.yml` config file somewhere on the Pi (e.g. `~/astromech/config/droids.yml`):

```yaml
droids:
  - alias: r2-t2
    mac_address: "F7:E6:74:95:E5:53"
    personality: resistance_blue
    type: r2
    home_assistant_entity: binary_sensor.r2_t2
```

Each droid entry requires:
- `alias` - friendly name used in API URLs
- `mac_address` - BLE MAC address of the droid
- `personality` - personality chip identifier
- `type` - `r2` or `bb`
- `home_assistant_entity` - (optional) HA entity ID for availability reporting

## Building and Running

Clone the repo so that `libastromech/` and `astromech_server/` are sibling directories (the Docker build context needs both):

```
repo/
  libastromech/
  astromech_server/
```

Build and run:

```bash
cd astromech_server
bin/run_docker.sh /path/to/config/dir
```

This builds the image, removes any existing container, and starts a new one with `--restart unless-stopped` so it survives reboots automatically.

### Manual docker commands

Build:

```bash
docker build -t astromech-server -f astromech_server/Dockerfile .
```

Run (from the parent directory containing both `libastromech/` and `astromech_server/`):

```bash
docker run -d \
    --name astromech-server \
    --restart unless-stopped \
    --net=host \
    --privileged \
    -v /var/run/dbus:/var/run/dbus \
    -v /path/to/config/dir:/config:ro \
    astromech-server
```

The flags explained:
- `--restart unless-stopped` - restarts the container on crash or reboot (only stops if you explicitly `docker stop` it)
- `--net=host` - required for BLE and beacon broadcasting
- `--privileged` - required for Bluetooth HCI access (`hcitool`)
- `-v /var/run/dbus:/var/run/dbus` - shares the host D-Bus socket for BlueZ
- `-v /path/to/config:/config:ro` - mounts your `droids.yml` config directory

## Managing the Container

```bash
# View logs
docker logs -f astromech-server

# Stop
docker stop astromech-server

# Start again (after explicit stop)
docker start astromech-server

# Restart
docker restart astromech-server

# Remove entirely
docker rm -f astromech-server
```

## API

The server listens on port 5050.

- `POST /droids/<droid_id>/beep/<sound_id>` - play a sound. Optional `?turn_head` triggers a head look-around.
- `POST /droids/<droid_id>/demo` - run a demo sequence with head movement and sounds.

## Deprecated

The systemd service approach (`astromech.service`, `bin/install.sh`, `bin/deploy.sh`, `bin/astromech_service.sh`) is deprecated. Use the Docker container instead.
