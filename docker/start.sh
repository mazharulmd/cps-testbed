#!/bin/bash
# Starts the Node-RED dashboard (1880) and the experiment web app (8080); exits if either stops.
mkdir -p /home/ubuntu/cps-testbed/results/runs
node-red -u /home/ubuntu/.node-red &
cd /home/ubuntu/cps-testbed/webapp && /home/ubuntu/cps-env-ubuntu/bin/uvicorn app:app --host 0.0.0.0 --port 8080 &
wait -n
exit $?
