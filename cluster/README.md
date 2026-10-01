# CPS testbed on a cluster

This directory turns the testbed into a cluster: GridPACK runs as an MPI job spread over
several machines, the HELICS federates (grid, NS-3 network, control center) can sit on
different nodes, and users upload grid models and scenario files and look at the results
in the Node-RED dashboard from their browser.

```
                     browser (remote user)
                            │  Node-RED dashboard :1880  ·  experiment API :8080
┌───────────────────────────▼────────────────────────── head ─┐
│ Node-RED: Experiments / Results / IEEE 14 console           │
│ experiment API: queue, grid + scenario uploads, results     │
│ HELICS broker (one per experiment, own port)                │
│ grid federate ──stdin/stdout──► mpirun ─┐                   │
└─────────────────────────────────────────┼───────────────────┘
          HELICS (ZMQ/TCP)                │ MPI (ssh launch, TCP)
┌──────────────── node1 ──────┐  ┌────────▼──── node1 … nodeN ──┐
│ NS-3 network federate       │  │ pf_server ranks: GridPACK     │
│ (PMUs, links, PDC, attacks) │  │ power flow on a partitioned   │
├──────────────── node2 ──────┤  │ network (ParMETIS, PETSc)     │
│ control-center federate     │  └───────────────────────────────┘
└─────────────────────────────┘        /shared: runs, grids, keys (NFS / volume)
```

## What runs where

| Part | Code | Notes |
|---|---|---|
| MPI power flow | `gridpack/pf_server/pf_server.cpp` | Started once per experiment with `mpirun -np N`. GridPACK reads and partitions the network once; every grid step only the changed loads and generator setpoints are sent to rank 0, broadcast, applied and solved. Voltages are gathered back to rank 0. |
| Grid federate | `federates/grid_fed.py`, `cpslib/gridpack.py` (`GridPackMPISolver`) | Drives `pf_server` over its stdin/stdout. Logs the whole step time and the MPI solve time of every step (`grid_steps.csv`). |
| Placement of federates | `federates/cpslib/cluster.py`, `run_experiment.py` | Reads `/shared/cluster.json`; starts the broker and each federate on its node over ssh; each experiment gets its own HELICS port so several can run at once. |
| Scheduling | `webapp/app.py` | Up to `CPS_MAX_JOBS` experiments at once, but a run starts only when its GridPACK ranks fit in the free MPI slots; the others wait in the queue ("waiting for N MPI slots"). MPI ranks busy-wait, so oversubscribing the slots made two parallel 4-rank runs about ten times slower (150 s instead of 13 s each). |
| Uploads | `federates/cpslib/grids.py`, `webapp/scenario.py` | MATPOWER `.m` (or testbed `topology.json`) grid models; YAML/JSON scenario files (`webapp/scenario_template.yaml`). |
| Dashboard | `node-red/flows.json` (tab *CPS Cluster*) | Experiments page: cluster nodes, uploads, grid list, queue. Results page: runs, summary, charts (voltages, chi-square, GridPACK time per step, latency, PDC completeness, per-PMU delivery), commands. |
| Image | `cluster/Dockerfile` | Built from source on Ubuntu 24.04: OpenMPI 4.1, PETSc 3.19 (MUMPS), ParMETIS, Global Arrays 5.9, GridPACK 3.5, HELICS 3.6.1, NS-3.48, Node-RED 4.1 + Dashboard 2. One image for every node. |

## Try it on one machine (virtual cluster)

```bash
docker build -f cluster/Dockerfile -t cps-testbed-cluster .      # about 1 hour the first time
docker compose -f cluster/docker-compose.yml up -d
```

`docker-compose.yml` starts a head and two compute nodes (`node1`, `node2`, 2 MPI slots
each). GridPACK runs on 4 MPI ranks across both nodes, NS-3 on `node1` and the control center
on `node2`. Open:

- Dashboard: http://localhost:1880/dashboard/experiments
- API (and its documentation): http://localhost:8080/docs

Set `CPS_WEB_PASSWORD` and `NODERED_ADMIN_HASH` (see the main README) before exposing the
ports to anyone else.

## Using it

1. **Grid model (optional).** On *Experiments*, upload a MATPOWER case (`.m`). The testbed
   checks the power flow, computes the optimal PMU placement and lists the grid with an id
   such as `case_activsg2000-12345`. PSS/E `.raw` files: convert them in MATPOWER first
   (`mpc = psse2mpc('grid.raw'); savecase('grid.m', mpc)`).
2. **Scenario.** Download the *scenario template*, edit it (grid, duration, `mpi_np`, network,
   event, attack, control) and upload it. A file can hold several experiments under
   `scenarios:`. Each one is validated, queued and run on the cluster.
3. **Results.** The *Results* page opens each finished run: summary figures, voltage and
   chi-square charts, GridPACK solve time per step for the chosen number of MPI ranks, network
   latency and delivery, and the commands sent to the grid. Raw files are in
   `/shared/runs/<run id>/`.

The API does the same for scripts:

```bash
curl -F file=@case_ACTIVSg2000.m http://localhost:8080/api/grids/file
curl -F file=@my_scenario.yaml   http://localhost:8080/api/scenarios/file
curl http://localhost:8080/api/runs
```

## Real machines

Use the same image (or the same build steps) on every machine and give them:

1. **A shared directory** mounted at `/shared` on all nodes (NFS or similar). Runs, uploaded
   grids, the hostfile and the cluster's SSH key live there.
2. **Name resolution and open TCP** between the nodes (MPI, HELICS ports 23500 and up, ssh).
3. **The role variables** of `docker-compose.yml`: `CPS_ROLE=node` on compute nodes;
   `CPS_ROLE=head` plus `CPS_NODES=host1:16,host2:16`, `CPS_PLACE_NS3`, `CPS_PLACE_CC`,
   `CPS_MPI_NP`, `CPS_MAX_JOBS` on the head. With Docker on each machine use
   `--network host` so that MPI and HELICS see the real interfaces, and set
   `OMPI_MCA_btl_tcp_if_include` / `OMPI_MCA_oob_tcp_if_include` to the cluster interface.

The head writes `/shared/cluster.json` and `/shared/hostfile` at start-up; edit the
variables and restart the head to change the layout. Remote users reach the dashboard through
the institution's VPN or an SSH tunnel to the head, as described in the user guide.

## Tested

On the virtual cluster (head + 2 nodes, all three containers on one 4-core machine):

| Experiment | Result |
|---|---|
| IEEE 118, AVR fault at gen 49 (t = 4 s) + simple FDI on bus 49, GridPACK on 4 ranks (node1 + node2), NS-3 on node1, control center on node2 | Same outcome as the single-server testbed and the user guide example: violation 0.5 s, FDI detected in one frame (0.033 s), PMU 49 removed, command issued at 4.067 s, delivered at 4.107 s, applied at 4.5 s; 9568/9568 frames delivered |
| ACTIVSg2000 (2000-bus Texas grid, uploaded as MATPOWER `.m`), 512 PMUs, AVR fault at gen 1004 + simple FDI | 76 288 frames delivered; violation corrected within one grid step (0.5 s). The FDI falsifies a current channel of PMU 3133 that is a critical measurement, so it is not detected (minimum placement; see the main README) |
| Two ACTIVSg2000 experiments queued from one scenario file | Ran at the same time on HELICS ports 23600 and 23700, both completed correctly |
| IEEE 118, AVR fault + delay attack (100 ms) on the PMUs around bus 49 | Violation 5.5 s, PMUs 45 and 49 delayed, 49.7% complete PDC sets, as in the main README |
| IEEE 118, AVR fault + 5% packet loss | 18.1% complete PDC sets, violation still corrected in 0.5 s, as in the main README |
| IEEE 118, 60% load step at bus 59, GridPACK (4 ranks) and built-in solver | True bus voltages identical to six decimals at every step |
| Legacy IEEE 14 console script | 13/14 delivered, bus 8 over-voltage detected, as before |

`pf_server` against the testbed's Newton-Raphson solver (four operating points with load and
setpoint changes): IEEE 118 and ACTIVSg2000 agree to 5×10⁻¹⁰ pu, ACTIVSg10k to 6×10⁻⁵ pu.
MPI solve time per grid step:

| Grid | 1 rank | 2 ranks | 4 ranks |
|---|---|---|---|
| IEEE 118, ranks in one container | 6–16 ms | 15–27 ms | 15–31 ms |
| IEEE 118, 4 ranks split over node1 and node2 | | | 61–71 ms |
| ACTIVSg2000, one container | 104–120 ms | 78–116 ms | 55–97 ms |
| ACTIVSg10k, one container | 526–638 ms | 452–624 ms | 356–508 ms |

Small grids are fastest on one rank: the work per solve is tiny and every extra rank adds MPI
messages (about 60 ms per solve when the ranks span two containers over TCP). The 10 000-bus
grid gets faster with more ranks even on four shared cores; on separate machines with their
own cores the gain is larger. When several co-simulations run at once on the same few cores,
GridPACK's times rise because MPI ranks, NS-3 and the control center compete for the CPU.

## Limits

- The grid model is quasi-steady-state (power flow every grid step), as in the rest of the
  testbed. Small grids (IEEE 14 to 300) solve in milliseconds, so more MPI ranks do not make
  them faster; the cluster pays off for large grids, long or many experiments.
- Uploaded grids: MATPOWER `.m` and testbed `topology.json`. PSS/E is read through MATPOWER's
  converter.
- The SSH key of the virtual cluster is created at first start and shared through `/shared`;
  on real machines use the site's own key management if it has one.
