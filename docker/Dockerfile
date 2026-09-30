# CPS testbed image, built from this repo on top of the prebuilt base image
# (compiled HELICS, GridPACK and NS-3, ~1.2 GB, too large for the repo).
#
#   docker build -f docker/Dockerfile -t cps-testbed:local .
#
# Stage 1 compiles what the base image is missing: the PETSc 3.16 library that
# GridPACK's pf.x links against, and the multi-PMU NS-3 federate (helicstest).
ARG BASE_IMAGE=ghcr.io/mazharulmd/cps-testbed:latest

FROM ${BASE_IMAGE} AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gfortran cmake ninja-build pkg-config git wget ca-certificates \
      python3-dev libopenmpi-dev openmpi-bin libboost-dev \
      libsqlite3-dev libgtk-3-dev libgsl-dev libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
COPY docker/build_petsc.sh /tmp/build_petsc.sh
RUN mkdir -p /home/ubuntu/software/petsc && bash /tmp/build_petsc.sh \
    && rm -rf /home/ubuntu/software/petsc/petsc-3.16.6 /home/ubuntu/software/petsc/petsc-3.16.6.tar.gz
COPY ns3-scratch/helicstest/ /home/ubuntu/software/ns-3/scratch/helicstest/
RUN cd /home/ubuntu/software/ns-3 && ./ns3 build helicstest

FROM ${BASE_IMAGE}
WORKDIR /home/ubuntu
COPY --from=build /home/ubuntu/software/petsc/install_for_gridpack /home/ubuntu/software/petsc/install_for_gridpack
COPY --from=build /home/ubuntu/software/ns-3/build/lib/ /home/ubuntu/software/ns-3/build/lib/
COPY --from=build /home/ubuntu/software/ns-3/build/scratch/helicstest/ns3-dev-helicstest /home/ubuntu/software/ns-3/build/scratch/helicstest/ns3-dev-helicstest
COPY ns3-scratch/helicstest/ /home/ubuntu/software/ns-3/scratch/helicstest/
ENV LD_LIBRARY_PATH=/home/ubuntu/software/petsc/install_for_gridpack/lib:/home/ubuntu/software/helics-cpp-install/lib:/home/ubuntu/software/GridPACK_install/lib:/home/ubuntu/software/ns-3/build/lib

RUN /home/ubuntu/cps-env-ubuntu/bin/pip install --no-cache-dir scipy fastapi "uvicorn[standard]"

# legacy single-PMU demo (Node-RED dashboard)
COPY scenario/run_scenario.sh scenario/run_scenario_docker.sh scenario/plot_voltages.py scenario/cps_dashboard_flow.json /home/ubuntu/cps-testbed/
COPY federates/gridpack_fed.py federates/gridpack_fed.json /home/ubuntu/
COPY federates/pf14/ /home/ubuntu/cps-work/pf14/
COPY node-red/flows.json node-red/settings.js node-red/package.json /home/ubuntu/.node-red/

# multi-PMU co-simulation and web application
COPY cases/ /home/ubuntu/cps-testbed/cases/
COPY federates/ /home/ubuntu/cps-testbed/federates/
COPY webapp/ /home/ubuntu/cps-testbed/webapp/
COPY tools/ /home/ubuntu/cps-testbed/tools/
COPY docker/start.sh /home/ubuntu/start.sh
RUN chmod +x /home/ubuntu/cps-testbed/*.sh /home/ubuntu/start.sh \
    && mkdir -p /home/ubuntu/cps-testbed/results/runs

EXPOSE 1880 8080
CMD ["/home/ubuntu/start.sh"]
