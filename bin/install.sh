#!/usr/bin/env bash
set -e

export CODE_BASE=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )/..
cd $CODE_BASE
pwd

scp -r ../astromech_server r2t2:code/

ssh r2t2 "mkdir -p ~/code/virtualenvs/; python3 -m venv ~/code/virtualenvs/astromech_server"
ssh r2t2 "cd code/astromech_server; sudo cp astromech.service /etc/systemd/system/; sudo systemctl enable astromech; sudo systemctl start astromech"
