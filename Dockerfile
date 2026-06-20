FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends bluez dbus sudo && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY libastromech /app/libastromech
RUN pip install --no-cache-dir /app/libastromech

COPY astromech_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY astromech_server/src /app/src

WORKDIR /app/src
CMD ["python", "server.py"]
