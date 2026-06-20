#!/usr/bin/env bash
# DEPRECATED: Use bin/run_docker.sh instead. See README.md.
echo "WARNING: deploy.sh is deprecated. Use bin/run_docker.sh instead." >&2
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
