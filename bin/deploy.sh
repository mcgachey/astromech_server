#!/usr/bin/env bash
set -e

export CODE_BASE=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )/..
cd $CODE_BASE
pwd

mkdir /tmp/astromech
cp -r src /tmp/astromech
cp -r bin /tmp/astromech
cp -r requirements.txt /tmp/astromech
cp -r astromech.service /tmp/astromech

scp -r /tmp/astromech/* r2t2:~/code/astromech_server
rm -rf /tmp/astromech

ssh r2t2 "sudo service astromech restart"
