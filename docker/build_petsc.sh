#!/bin/bash
# Rebuilds the PETSc 3.16 that GridPACK's pf.x links against (real scalars), at the path it expects.
# Run inside the dev image (docker/Dockerfile.dev) as root, with a volume mounted at
# /home/ubuntu/software/petsc so the install persists:
#   docker run --rm -v $PWD/petsc:/home/ubuntu/software/petsc -v $PWD/docker/build_petsc.sh:/b.sh:ro \
#     --entrypoint bash cps-testbed:dev /b.sh
set -e
cd /home/ubuntu/software/petsc
[ -d petsc-3.16.6 ] || { wget -q https://web.cels.anl.gov/projects/petsc/download/release-snapshots/petsc-3.16.6.tar.gz && tar xzf petsc-3.16.6.tar.gz; }
cd petsc-3.16.6
export PETSC_DIR=$PWD PETSC_ARCH=arch-gridpack-real
python3 ./configure --prefix=/home/ubuntu/software/petsc/install_for_gridpack \
  --with-cc=mpicc --with-cxx=mpicxx --with-fc=mpif90 \
  --with-scalar-type=real --with-shared-libraries=1 --with-debugging=0 \
  --download-superlu_dist --download-parmetis --download-metis \
  --download-suitesparse --download-f2cblaslapack \
  COPTFLAGS=-O2 CXXOPTFLAGS=-O2 FOPTFLAGS=-O2
make PETSC_DIR=$PWD PETSC_ARCH=arch-gridpack-real all -j16
make PETSC_DIR=$PWD PETSC_ARCH=arch-gridpack-real install
echo PETSC_BUILD_DONE
