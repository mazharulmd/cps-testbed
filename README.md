# CPS Testbed — Synchrophasor Co-Simulation

A cyber-physical co-simulation testbed for synchrophasor (PMU) monitoring and control of a power grid, built for the NSU–PGCB project *Remotely Accessible Cyber-Physical System Testbed and Open Architecture Synchrophasor Systems* (EPRC/58-2018-007-01). Three federates are time-synchronized by **HELICS**:

| Federate | Role | Code |
|---|---|---|
| **Grid** (GridPACK) | Re-solves the power flow every grid step with varying load and events; applies control commands; publishes the true phasors each PMU measures | `federates/grid_fed.py` |
| **Network** (NS-3) | PMUs at the optimal placement buses send frames at 30–60 fps over their own links (latency, jitter, loss) to a PDC with a wait window; attacks; commands travel back to generator nodes | `ns3-scratch/helicstest/helicstest.cc` |
| **Control center** | Linear PMU state estimation, chi-square bad data detection with suspicious-PMU removal, voltage limit checks, generator setpoint control | `federates/cc_fed.py` |

A **web application** (`webapp/`, port 8080) lets users pick a bus system and scenario, queue experiments and inspect the results. The original single-PMU IEEE 14-bus demo and its **Node-RED** dashboard (port 1880) still work unchanged.

```
 GridPACK grid ──phasors──▶ NS-3: PMUs ─▶ links ─▶ PDC ──aligned sets──▶ control center
      ▲                                                                   │
      └──── setpoint applied ◀── NS-3: generator node ◀── command ────────┘
```

📘 **User guide:** [CPS_Testbed_User_Guide.pdf](docs/CPS_Testbed_User_Guide.pdf) ([Word version](docs/CPS_Testbed_User_Guide.docx)): how to open and use the web app and the Node-RED dashboard, every input and output explained, worked examples.

📄 **Technical report:** [CPS_Testbed_Technical_Report_v2.pdf](docs/CPS_Testbed_Technical_Report_v2.pdf) ([Word version](docs/CPS_Testbed_Technical_Report_v2.docx)): architecture, validation, PMU placement and experiment results for the single-PMU prototype and the extended multi-PMU testbed.

## Features

- **Bus systems:** IEEE 14, 30, 39, 57, 118 and 300 (`cases/`, generated from MATPOWER data by `tools/make_cases.py`). GridPACK agrees with an independent Newton-Raphson solver to within 5×10⁻⁷ pu on all six.
- **Optimal PMU placement** (integer linear program): minimum PMUs for full observability (4 / 10 / 13 / 17 / 32 / 87 PMUs), or a redundant placement where every bus is seen by two PMUs.
- **Network:** per-link latency with spread, jitter, packet loss, PDC wait window, reporting rate.
- **Attacks:** false data injection (simple: one channel; stealthy: consistent across all channels touching the target bus, adaptive to the live state), packet drop, delay.
- **Defenses:** chi-square bad data detection with largest-normalized-residual PMU removal; control is held while bad data cannot be cleaned; redundant placement.
- **Grid events:** generator AVR setpoint fault, load step.
- **Metrics:** delivery ratio and latency percentiles, PDC set completeness, state estimation error, false alarms, detection rate and time to detect, true violation time, control commands.

## Example results (IEEE 118-bus, 10 s, AVR fault at generator 49 → 1.12 pu at t = 4 s)

| Scenario | Violation time | What happened |
|---|---|---|
| No control | 6.5 s | Violation persists to the end |
| Control on | 0.5 s | Control center lowers generator 49 setpoint within one grid step |
| 5% packet loss | 0.5 s | Only 18% of PDC sets complete, but estimation stays usable |
| Simple FDI on bus 49 | 0.5 s | Detected immediately; falsified PMU removed; control still acts |
| Stealthy FDI on bus 49 | 0.5 s | Not detected (2 PMUs compromised), but neighbour bus 48 still reveals the over-voltage |
| Delay attack (100 ms) on PMUs 45, 49 | 5.5 s | Frames miss the PDC window; bus 49 unobserved; violation missed |

With minimum placement, some buses are observed through a single *critical measurement*. Falsifying it is invisible to bad data detection (e.g. IEEE 14 bus 8, IEEE 30 bus 13); redundant placement removes that blind spot.

## Running experiments

Web app: open `http://localhost:8080` (see *Run it locally*), choose a preset or parameters, **Run experiment**.

Command line (inside the container):

```bash
cd /home/ubuntu/cps-testbed/federates
/home/ubuntu/cps-env-ubuntu/bin/python run_experiment.py --case 118 --duration 10 \
    --event avr:49:1.12:4 --attack fdi-stealthy --target 49 --fake 1.02 --attack-start 4 --attack-end 9
```

`run_experiment.py --help` lists all options. Each run writes to `results/runs/<timestamp>_<name>/`:

| File | Contents |
|---|---|
| `summary.json` | Scored results (network, grid, control center, attack) |
| `meta.json`, `run_config.json`, `ns3_config.json` | Inputs, PMU placement, attack plan |
| `frames.csv` | Every PMU frame: send/arrival time, latency, status, attacked |
| `cc_log.csv`, `cc_estimates.csv` | Per measurement set: chi-square test, alarms, removed PMUs; estimated voltages |
| `grid_truth.csv`, `grid_steps.csv`, `commands_applied.csv` | True voltages, solver status, commands applied to the grid |

### Limitations

- Power flow is quasi-steady-state (no dynamics); the frames are JSON, not binary IEEE C37.118; the network is a star of PMU links around one PDC.
- Frame authentication is not implemented.
- The stealthy attacker hides one bus; neighbouring buses can still reveal a violation.

## Repository layout

```
cases/           IEEE 14–300 bus GridPACK inputs, topology, reference solutions
federates/       grid_fed.py, cc_fed.py, run_experiment.py, cpslib/ (network, placement, estimation, attacks)
ns3-scratch/     NS-3 federate (helicstest.cc: legacy single-PMU mode + multi-PMU --config mode)
webapp/          FastAPI app + browser UI
tools/           make_cases.py
scenario/        legacy single-PMU scripts and sample results
node-red/        legacy dashboard flows and settings
docker/          Dockerfile (multi-stage), Dockerfile.dev, build_petsc.sh, start.sh
docs/            technical report and user guide (PDF and Word)
```

## Run it locally (Docker)

The whole testbed (HELICS, GridPACK, NS-3, the federates, the web app and the Node-RED dashboard) is published as a public container image:

**📦 [`ghcr.io/mazharulmd/cps-testbed`](https://github.com/mazharulmd/cps-testbed/pkgs/container/cps-testbed)**

| Tag | Contents | Use it for |
|---|---|---|
| `latest` | The current full testbed: live GridPACK, IEEE 14–300 bus cases, multi-PMU NS-3 network, control center, web app (8080) and Node-RED dashboard (1880) | Running the testbed |
| `v2` | The same image as `latest` at the time of the multi-PMU release, under a fixed name | Reproducing published results; it will not change when `latest` is updated |
| `base` | The earlier prebuilt image with the compiled HELICS, GridPACK and NS-3 and the legacy single-PMU demo only | Building from this repo (`docker/Dockerfile` layers onto it); not meant to be run directly |

The compiled HELICS, GridPACK and NS-3 builds (~1.2 GB) are not stored in this repo; they are inside the image.

### Requirements

- **Docker**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows 10/11 (WSL 2 backend) or macOS, or Docker Engine on Linux.
- **x86-64 (amd64) machine.** On Apple Silicon Macs, add `--platform linux/amd64` to `docker pull` and `docker run`; it runs under emulation and is slower.
- About **2 GB of download** and **5 GB of free disk space**.

### 1. Pull the image

```bash
docker pull ghcr.io/mazharulmd/cps-testbed:latest
```

To pin the exact version used for the results in this README and the technical report, use `ghcr.io/mazharulmd/cps-testbed:v2` in place of `:latest` in all commands below.

### 2. Start the container

**Quick start, no login.** Use this only on your own computer:

```bash
docker run -d --name cps-testbed -p 1880:1880 -p 8080:8080 ghcr.io/mazharulmd/cps-testbed:latest
```

**With a login (recommended).** For the web app, pass a password as `CPS_WEB_PASSWORD` (username `admin`, or set `CPS_WEB_USER`). For Node-RED, create a bcrypt hash of your chosen password and pass it as `NODERED_ADMIN_HASH` (username `admin`, or set `NODERED_ADMIN_USER`).

Linux / macOS (bash):

```bash
HASH=$(docker run --rm ghcr.io/mazharulmd/cps-testbed:latest node -e 'console.log(require("/usr/lib/node_modules/node-red/node_modules/bcryptjs").hashSync(process.argv[1], 8))' 'your-password')

docker run -d --name cps-testbed -p 1880:1880 -p 8080:8080 \
  -e NODERED_ADMIN_HASH="$HASH" -e CPS_WEB_PASSWORD="your-password" ghcr.io/mazharulmd/cps-testbed:latest
```

Windows (PowerShell):

```powershell
$HASH = docker run --rm ghcr.io/mazharulmd/cps-testbed:latest node -e "console.log(require('/usr/lib/node_modules/node-red/node_modules/bcryptjs').hashSync(process.argv[1], 8))" "your-password"

docker run -d --name cps-testbed -p 1880:1880 -p 8080:8080 -e NODERED_ADMIN_HASH=$HASH -e CPS_WEB_PASSWORD="your-password" ghcr.io/mazharulmd/cps-testbed:latest
```

> ⚠️ Without `NODERED_ADMIN_HASH` / `CPS_WEB_PASSWORD`, anyone who can reach ports 1880 / 8080 can edit flows, run experiments and use the server's CPU. Never expose them to the internet that way.

### 3. Open the web app and the dashboard

The services take a few seconds to start. Then open:

- **Experiment web app:** http://localhost:8080 — choose a bus system and scenario (or a preset), click **Run experiment**; results and charts appear when the run finishes (an IEEE 118-bus, 10 s run takes about 25 s).
- **Legacy operator dashboard (IEEE 14, single PMU):** http://localhost:1880/dashboard/console
- **Node-RED editor:** http://localhost:1880

### 4. Run a legacy scenario

In the **Run Scenario** panel at the top of the Node-RED dashboard:

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

Web app experiments are written inside the container under `/home/ubuntu/cps-testbed/results/runs/` (legacy dashboard runs under `/home/ubuntu/cps-testbed/results/`). To keep them when the container is removed or updated, add a volume to the `docker run` command in step 2:

```bash
-v "$PWD/cps-results:/home/ubuntu/cps-testbed/results/runs"
```

Or copy them to your computer:

```bash
docker cp cps-testbed:/home/ubuntu/cps-testbed/results ./results
```

### Troubleshooting

- **Port 8080 or 1880 already in use:** map a different local port, e.g. `-p 18080:8080` or `-p 18800:1880`, then open http://localhost:18080 or http://localhost:18800/dashboard/console.
- **`docker: command not found` / cannot connect to the Docker daemon:** start Docker Desktop, or on Linux run `sudo systemctl start docker`.
- **Name already in use (`cps-testbed`):** remove the old container first with `docker rm -f cps-testbed`.

### Build from this repo (optional)

To try changes to the code in this repo, build your own image. `docker/Dockerfile` starts from `ghcr.io/mazharulmd/cps-testbed:base`, compiles PETSc for GridPACK and the NS-3 federate, and adds the cases, federates and web app. The first build takes about 25 minutes (mostly PETSc); later builds reuse the cached layers.

```bash
git clone https://github.com/mazharulmd/cps-testbed.git
cd cps-testbed
docker build -f docker/Dockerfile -t cps-testbed:local .
docker run -d --name cps-testbed -p 1880:1880 -p 8080:8080 -e CPS_WEB_PASSWORD="your-password" cps-testbed:local
```

For development with compilers available (for example to rebuild NS-3 interactively), build `docker/Dockerfile.dev`, which also starts from `:base`.

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

Changes to `helicstest.cc` are compiled by `docker/Dockerfile` when you build the image. The runtime image itself contains the NS-3 source and compiled binaries but no compiler; to rebuild NS-3 by hand use the development image (`docker/Dockerfile.dev`).

## Licensing

The Docker image bundles third-party software under its own licenses, including NS-3 (GPLv2, source included in the image under `/home/ubuntu/software/ns-3`), HELICS (BSD-3-Clause), GridPACK (BSD-style) and Node-RED (Apache-2.0).
