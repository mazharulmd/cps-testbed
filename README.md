# CPS Testbed — Synchrophasor Co-Simulation

A cyber-physical co-simulation of PMU measurements travelling from the power grid to a control center (PDC). The simulators are coupled through **HELICS**:

| Component | Role | Where |
|---|---|---|
| **HELICS** 3.6.1 | Co-simulation broker; time-syncs the federates | `helics_broker` in the image |
| **GridPACK** | IEEE 14-bus power flow (grid side) | `federates/gridpack_fed.py` |
| **NS-3** | PMU → PDC UDP network: latency, packet loss, false-data-injection attack | `ns3-scratch/helicstest/helicstest.cc` |
| **Node-RED** + Dashboard 2.0 | Operator console: run scenarios, view results | `node-red/flows.json` |

> **Note:** `gridpack_fed.py` currently publishes a saved GridPACK power-flow solution (`federates/pf14/pf_IEEE14_buses.csv`). It does not re-run GridPACK during a scenario, so control commands are logged but do not change the grid state.

## How a scenario runs

1. `helics_broker` starts, expecting 2 federates.
2. The GridPACK federate publishes one bus voltage per time step.
3. The NS-3 federate sends each value as a PMU packet across a point-to-point link to the PDC. If a voltage exceeds 1.08 pu, it sends a `REDUCE_VOLTAGE@busN` command back to GridPACK.
4. NS-3 writes `results/last_compare.csv` and `results/last_summary.json`, and the dashboard reads them.

## Repository layout

```
scenario/        run_scenario*.sh, plot_voltages.py, sample results
federates/       GridPACK HELICS federate, its config, IEEE 14-bus input + power-flow output
ns3-scratch/     NS-3 HELICS federate source (helicstest.cc)
node-red/        Dashboard flows, settings.js, package.json
docker/          Dockerfile that layers this repo onto the prebuilt base image
```

## Running

The compiled HELICS, GridPACK and NS-3 builds (~1.2 GB) are not stored in this repo. They ship in the prebuilt Docker image `cps-testbed:dashboard`, exported as `cps-testbed-dashboard.tar.gz`.

```bash
docker load < cps-testbed-dashboard.tar.gz

# optional: rebuild with the files from this repo
docker build -f docker/Dockerfile -t cps-testbed:local .

# set a dashboard login (bcrypt hash of your password)
HASH=$(docker run --rm cps-testbed:local node -e 'console.log(require("/usr/lib/node_modules/node-red/node_modules/bcryptjs").hashSync(process.argv[1], 8))' 'your-password')

docker run -d --name cps-testbed -p 1880:1880 -e NODERED_ADMIN_HASH="$HASH" cps-testbed:local
```

- Dashboard: http://localhost:1880/dashboard/console
- Node-RED editor: http://localhost:1880

If `NODERED_ADMIN_HASH` is not set, Node-RED runs **without a login**. Don't expose it to the internet that way.

### Command line

```bash
docker exec cps-testbed /home/ubuntu/cps-testbed/run_scenario_docker.sh \
  --latency=50 --loss=0.2 --name=myrun [--attack=1] [--droppmu=8]
```

| Option | Meaning |
|---|---|
| `--latency` | Link latency (ms) |
| `--loss` | Packet loss rate, 0–1 |
| `--attack=1` | Enable false-data injection (hides the bus 8 over-voltage) |
| `--droppmu=N` | Drop bus N's measurement |
| `--name` | Scenario name used for the result files |

Changes to `helicstest.cc` require rebuilding NS-3 (`./ns3 build`) in an environment that has the NS-3 build toolchain; the runtime image contains only the compiled binary.
