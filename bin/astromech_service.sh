#!/usr/bin/env bash
# DEPRECATED: Use bin/run_docker.sh instead. See README.md.

cd ~/code/astromech_server
source ~/code/virtualenvs/astromech_server/bin/activate
pip install -r requirements.txt
python src/server.py
