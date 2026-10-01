# CPS testbed cluster node, built entirely from source (no prebuilt base image).
# One image serves every node of the cluster; cluster/entrypoint.sh picks the role.
#
#   docker build -f cluster/Dockerfile -t cps-testbed-cluster .
#
# Contents: OpenMPI 4.1, PETSc 3.19 (Ubuntu, with MUMPS), ParMETIS, Global Arrays 5.9,
# GridPACK 3.5 + the testbed's MPI power-flow server, HELICS 3.6.1, NS-3 with the testbed's
# network federate, Python federates and API, Node-RED 4 with Dashboard 2, OpenSSH.
ARG BASE=ubuntu:24.04
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gfortran cmake ninja-build pkg-config git wget ca-certificates \
      python3 python3-dev python3-venv \
      openmpi-bin libopenmpi-dev petsc-dev libparmetis-dev libmetis-dev \
      libboost-dev libboost-mpi-dev libboost-serialization-dev libboost-random-dev \
      libboost-filesystem-dev libboost-system-dev libzmq3-dev \
      openssh-server openssh-client nodejs npm procps iproute2 less \
    && rm -rf /var/lib/apt/lists/*

ARG JOBS=4

# Global Arrays (GridPACK's distributed data layer), configured as in GridPACK's install script
RUN cd /tmp && wget -q https://github.com/GlobalArrays/ga/releases/download/v5.9/ga-5.9.tar.gz \
    && tar xzf ga-5.9.tar.gz && cd ga-5.9 \
    && ./configure --with-mpi-ts --disable-f77 --without-blas --without-lapack --without-scalapack \
         --enable-cxx --enable-i4 --enable-shared=yes --enable-static=no --prefix=/opt/ga \
         CFLAGS=-Wno-implicit-function-declaration \
    && make -j${JOBS} install && cd / && rm -rf /tmp/ga-5.9*

# GridPACK 3.5 (libraries and applications; unit tests off)
RUN git clone -q --depth 1 --branch v3.5 https://github.com/GridOPTICS/GridPACK /tmp/gridpack \
    && cmake -S /tmp/gridpack/src -B /tmp/gridpack/build -G Ninja \
         -D CMAKE_BUILD_TYPE=Release -D BUILD_SHARED_LIBS=ON \
         -D GRIDPACK_ENABLE_TESTS=OFF -D ENABLE_ENVIRONMENT_FROM_COMM=YES \
         -D GA_DIR=/opt/ga -D PETSC_DIR=/usr/lib/petsc -D PARMETIS_DIR=/usr \
         -D MPI_CXX_COMPILER=mpicxx -D MPI_C_COMPILER=mpicc -D MPIEXEC=mpiexec \
         -D CMAKE_INSTALL_PREFIX=/opt/gridpack \
    && cmake --build /tmp/gridpack/build -j ${JOBS} && cmake --install /tmp/gridpack/build \
    && rm -rf /tmp/gridpack

# HELICS 3.6.1 (C++ shared library and helics_broker)
RUN cd /tmp && wget -q https://github.com/GMLC-TDC/HELICS/releases/download/v3.6.1/Helics-v3.6.1-source.tar.gz \
    && mkdir helics && tar xzf Helics-v3.6.1-source.tar.gz -C helics \
    && cmake -S helics -B helics/build -G Ninja -D CMAKE_BUILD_TYPE=Release \
         -D HELICS_BUILD_CXX_SHARED_LIB=ON -D HELICS_BUILD_EXAMPLES=OFF -D HELICS_BUILD_TESTS=OFF \
         -D CMAKE_INSTALL_PREFIX=/opt/helics \
    && cmake --build helics/build -j ${JOBS} && cmake --install helics/build \
    && rm -rf /tmp/helics /tmp/Helics-*

ENV LD_LIBRARY_PATH=/opt/helics/lib:/opt/gridpack/lib:/opt/ga/lib \
    PATH=/opt/helics/bin:/opt/gridpack/bin:/opt/cps-venv/bin:${PATH}

# NS-3 with only the modules the network federate needs
ARG NS3_TAG=ns-3.48
RUN git clone -q --depth 1 --branch ${NS3_TAG} https://gitlab.com/nsnam/ns-3-dev.git /opt/ns-3 \
    && cd /opt/ns-3 \
    && ./ns3 configure --build-profile=optimized --disable-examples --disable-tests \
         --enable-modules="core;network;internet;point-to-point;applications" \
         -- -DCMAKE_CXX_FLAGS=-I/opt/helics/include \
            "-DCMAKE_EXE_LINKER_FLAGS=-L/opt/helics/lib -Wl,--no-as-needed -lhelicscpp -lhelics -Wl,--as-needed" \
    && ./ns3 build

# Python environment for the federates, the experiment API and the case tools
RUN python3 -m venv /opt/cps-venv \
    && /opt/cps-venv/bin/pip install --no-cache-dir helics==3.6.1 numpy scipy \
         fastapi "uvicorn[standard]" python-multipart pyyaml

# Node-RED 4 with FlowFuse Dashboard 2
COPY node-red/package.json /opt/node-red-data/package.json
RUN npm install -g --unsafe-perm node-red@4.1.11 \
    && cd /opt/node-red-data && npm install --omit=dev --no-audit --no-fund

# OpenSSH for MPI and remote federate launch between nodes (keys are created at start-up)
RUN mkdir -p /run/sshd \
    && printf 'PermitRootLogin prohibit-password\nPasswordAuthentication no\n' > /etc/ssh/sshd_config.d/cps.conf \
    && printf 'Host *\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n  LogLevel ERROR\n' > /etc/ssh/ssh_config.d/cps.conf

# OpenMPI inside containers: run as root, launch over ssh, no CMA single-copy
ENV OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
    OMPI_MCA_plm_rsh_agent=ssh OMPI_MCA_btl_vader_single_copy_mechanism=none \
    OMPI_MCA_btl_tcp_if_include=eth0 OMPI_MCA_oob_tcp_if_include=eth0 \
    OMPI_MCA_plm_rsh_no_tree_spawn=1 PRTE_MCA_plm_ssh_agent=ssh

# the testbed
COPY ns3-scratch/helicstest/ /opt/ns-3/scratch/helicstest/
RUN cd /opt/ns-3 && ./ns3 build helicstest \
    && ln -sf "$(find /opt/ns-3/build/scratch/helicstest -maxdepth 1 -type f -name '*helicstest*' | head -1)" \
         /opt/ns-3/helicstest
COPY gridpack/ /opt/cps-testbed/gridpack/
RUN cmake -S /opt/cps-testbed/gridpack/pf_server -B /tmp/pfs -D GRIDPACK_DIR=/opt/gridpack \
         -D CMAKE_INSTALL_PREFIX=/opt/gridpack \
    && cmake --build /tmp/pfs -j ${JOBS} && cmake --install /tmp/pfs && rm -rf /tmp/pfs
COPY cases/ /opt/cps-testbed/cases/
COPY federates/ /opt/cps-testbed/federates/
COPY webapp/ /opt/cps-testbed/webapp/
COPY tools/ /opt/cps-testbed/tools/
COPY cluster/ /opt/cps-testbed/cluster/
COPY node-red/flows.json node-red/settings.js /opt/node-red-data/

# legacy single-PMU IEEE 14 demo (Node-RED console): the paths its scripts expect
COPY scenario/run_scenario.sh scenario/run_scenario_docker.sh scenario/plot_voltages.py /home/ubuntu/cps-testbed/
COPY federates/gridpack_fed.py federates/gridpack_fed.json /home/ubuntu/
COPY federates/pf14/ /home/ubuntu/cps-work/pf14/
RUN mkdir -p /home/ubuntu/software /home/ubuntu/software/ns-3/build/scratch/helicstest \
    && ln -s /opt/helics /home/ubuntu/software/helics-cpp-install \
    && ln -s /opt/ns-3/build/lib /home/ubuntu/software/ns-3/build/lib \
    && ln -s /opt/ns-3/helicstest /home/ubuntu/software/ns-3/build/scratch/helicstest/ns3-dev-helicstest \
    && ln -s /opt/cps-venv /home/ubuntu/cps-env-ubuntu \
    && ln -s /shared/legacy /home/ubuntu/cps-testbed/results \
    && chmod +x /home/ubuntu/cps-testbed/*.sh /opt/cps-testbed/cluster/*.sh

ENV LD_LIBRARY_PATH=/opt/helics/lib:/opt/gridpack/lib:/opt/ga/lib:/opt/ns-3/build/lib \
    CPS_NS3_BIN=/opt/ns-3/helicstest CPS_PF_SERVER=/opt/gridpack/bin/pf_server \
    CPS_SHARED=/shared CPS_RESULTS=/shared/runs CPS_GRIDS=/shared/grids \
    CPS_CLUSTER_CONFIG=/shared/cluster.json
EXPOSE 1880 8080 22
ENTRYPOINT ["/opt/cps-testbed/cluster/entrypoint.sh"]
