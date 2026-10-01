# Builds pf_server against an installed GridPACK:
#   cmake -S gridpack/pf_server -B build -D GRIDPACK_DIR=/opt/gridpack && cmake --build build
cmake_minimum_required(VERSION 3.5)

if (NOT GRIDPACK_DIR)
  set(GRIDPACK_DIR /opt/gridpack CACHE PATH "GridPACK installation directory")
endif()

include("${GRIDPACK_DIR}/lib/GridPACK.cmake")

project(CPSPowerFlowServer)
enable_language(CXX)
gridpack_setup()

add_definitions(${GRIDPACK_DEFINITIONS})
include_directories(BEFORE ${GRIDPACK_INCLUDE_DIRS})

add_executable(pf_server pf_server.cpp)
target_link_libraries(pf_server ${GRIDPACK_LIBS})
install(TARGETS pf_server DESTINATION bin)
