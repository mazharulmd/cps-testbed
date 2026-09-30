# Layers this repo's scripts, flows and federates onto the prebuilt CPS testbed image.
# The base image carries the compiled HELICS, GridPACK and NS-3 builds (~1.2 GB),
# which are too large for the repo. Load it first, e.g.:
#   docker load < cps-testbed-dashboard.tar.gz
#
# Build (from the repo root):
#   docker build -f docker/Dockerfile -t cps-testbed:local .
ARG BASE_IMAGE=cps-testbed:dashboard
FROM ${BASE_IMAGE}

WORKDIR /home/ubuntu

COPY scenario/run_scenario.sh scenario/run_scenario_docker.sh scenario/plot_voltages.py scenario/cps_dashboard_flow.json /home/ubuntu/cps-testbed/
COPY federates/gridpack_fed.py federates/gridpack_fed.json /home/ubuntu/
COPY federates/pf14/ /home/ubuntu/cps-work/pf14/
COPY ns3-scratch/helicstest/helicstest.cc /home/ubuntu/software/ns-3/scratch/helicstest/helicstest.cc
COPY node-red/flows.json node-red/settings.js node-red/package.json /home/ubuntu/.node-red/

RUN chmod +x /home/ubuntu/cps-testbed/*.sh && mkdir -p /home/ubuntu/cps-testbed/results

EXPOSE 1880
CMD ["node-red", "-u", "/home/ubuntu/.node-red"]
