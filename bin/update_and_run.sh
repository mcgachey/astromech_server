docker ps | grep astro | awk '{print $1}' | xargs docker stop
cd ~/code/astromech_server
git pull
cd ~/code/libastromech/
git pull
cd -
./bin/run_docker.sh /home/mcgachey/code/astromech_server/config/
