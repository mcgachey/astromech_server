#!/usr/bin/env bash

cd ~/code/astromech_server
source ~/code/virtualenvs/astromech_server/bin/activate
pip install -r requirements.txt
python src/server.py
