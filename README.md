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

## Run it locally (Docker)

The whole testbed (HELICS, GridPACK, NS-3, the federates and the Node-RED dashboard) is published as a public container image:

**📦 [`ghcr.io/mazharulmd/cps-testbed`](https://github.com/mazharulmd/cps-testbed/pkgs/container/cps-testbed)**

The compiled HELICS, GridPACK and NS-3 builds (~1.2 GB) are not stored in this repo; they are inside the image.

### Requirements

- **Docker**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows 10/11 (WSL 2 backend) or macOS, or Docker Engine on Linux.
- **x86-64 (amd64) machine.** On Apple Silicon Macs, add `--platform linux/amd64` to `docker pull` and `docker run`; it runs under emulation and is slower.
- About **2 GB of download** and **3 GB of free disk space**.

### 1. Pull the image

```bash
docker pull ghcr.io/mazharulmd/cps-testbed:latest
```

### 2. Start the container

**Quick start, no login.** Use this only on your own computer:

```bash
docker run -d --name cps-testbed -p 1880:1880 ghcr.io/mazharulmd/cps-testbed:latest
```

**With a login (recommended).** Create a bcrypt hash of your chosen password, then pass it in as `NODERED_ADMIN_HASH`. The username is `admin`, or set `NODERED_ADMIN_USER`.

Linux / macOS (bash):

```bash
HASH=$(docker run --rm ghcr.io/mazharulmd/cps-testbed:latest node -e 'console.log(require("/usr/lib/node_modules/node-red/node_modules/bcryptjs").hashSync(process.argv[1], 8))' 'your-password')

docker run -d --name cps-testbed -p 1880:1880 -e NODERED_ADMIN_HASH="$HASH" ghcr.io/mazharulmd/cps-testbed:latest
```

Windows (PowerShell):

```powershell
$HASH = docker run --rm ghcr.io/mazharulmd/cps-testbed:latest node -e "console.log(require('/usr/lib/node_modules/node-red/node_modules/bcryptjs').hashSync(process.argv[1], 8))" "your-password"

docker run -d --name cps-testbed -p 1880:1880 -e NODERED_ADMIN_HASH=$HASH ghcr.io/mazharulmd/cps-testbed:latest
```

> ⚠️ Without `NODERED_ADMIN_HASH`, anyone who can reach port 1880 can edit flows and run commands in the container. Never expose it to the internet that way.

### 3. Open the dashboard

Node-RED takes a few seconds to start. Then open:

- **Operator dashboard:** http://localhost:1880/dashboard/console
- **Node-RED editor:** http://localhost:1880

### 4. Run a scenario

In the **Run Scenario** panel at the top of the dashboard:

1. Set a **scenario name**, **latency (ms)**, **loss (0–1)**, and optionally a bus to **drop** or the **FDI attack** switch.
2. Click **Run scenario**. A run takes about 10–15 seconds.
3. When it finishes, the voltage chart, delay chart, delivery gauge, metrics and per-bus table update automatically.

Try, for example:

| Scenario | Settings | What you should see |
|---|---|---|
| Baseline | latency 20, loss 0.2 | 13/14 delivered, bus 8 over-voltage detected, control command sent back to GridPACK |
| Congested network | latency 500 | Same detection, much higher end-to-end delay |
| False-data injection | latency 20, FDI attack on | Bus 8 violation hidden from the PDC, reported as a **missed violation** |
| Lost measurement | latency 20, drop bus 8 | 12/14 delivered; bus 8 never reaches the PDC, so its over-voltage goes undetected (0 violations seen) |

### 5. Stop, restart, update

```bash
docker stop cps-testbed        # stop
docker start cps-testbed       # start again (keeps results)
docker logs -f cps-testbed     # view Node-RED logs

# update to the newest image
docker rm -f cps-testbed
docker pull ghcr.io/mazharulmd/cps-testbed:latest
# ...then run the `docker run` command from step 2 again
```

Results are written inside the container under `/home/ubuntu/cps-testbed/results/`. To copy them to your computer:

```bash
docker cp cps-testbed:/home/ubuntu/cps-testbed/results ./results
```

### Troubleshooting

- **Port 1880 already in use:** map a different local port, e.g. `-p 18800:1880`, then open http://localhost:18800/dashboard/console.
- **`docker: command not found` / cannot connect to the Docker daemon:** start Docker Desktop, or on Linux run `sudo systemctl start docker`.
- **Name already in use (`cps-testbed`):** remove the old container first with `docker rm -f cps-testbed`.

### Build from this repo (optional)

To try changes to the scripts, federates or flows in this repo, layer them onto the published image:

```bash
git clone https://github.com/mazharulmd/cps-testbed.git
cd cps-testbed
docker build -f docker/Dockerfile -t cps-testbed:local .
docker run -d --name cps-testbed -p 1880:1880 cps-testbed:local
```

### Command line

Scenarios can also be run without the dashboard:

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

After a command-line run, click **Load Latest Scenario** in the Node-RED editor to show it on the dashboard.

Changes to `helicstest.cc` require rebuilding NS-3 (`./ns3 build`). The image contains the NS-3 source and compiled binaries but no compiler, so rebuild in an environment that has the NS-3 build toolchain.

## Licensing

The Docker image bundles third-party software under its own licenses, including NS-3 (GPLv2, source included in the image under `/home/ubuntu/software/ns-3`), HELICS (BSD-3-Clause), GridPACK (BSD-style) and Node-RED (Apache-2.0).
