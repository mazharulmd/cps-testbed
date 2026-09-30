#!/usr/bin/env python3
"""CPS testbed web application: configure, queue and inspect co-simulation experiments.

Runs one experiment at a time (federates share one HELICS broker) through
federates/run_experiment.py and serves the results as JSON for the browser UI.

Environment:
  CPS_WEB_USER / CPS_WEB_PASSWORD  HTTP basic auth (login disabled if no password is set)
  CPS_RESULTS                      results directory (default <repo>/results/runs)

Start: uvicorn app:app --host 0.0.0.0 --port 8080   (from this directory)
"""
import csv, json, os, queue, re, secrets, subprocess, sys, threading, time
from typing import Optional

import numpy as np
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
FED = os.path.join(ROOT, "federates")
CASES = os.environ.get("CPS_CASES", os.path.join(ROOT, "cases"))
RESULTS = os.environ.get("CPS_RESULTS", os.path.join(ROOT, "results", "runs"))
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, FED)
from cpslib.network import Network  # noqa: E402
from cpslib.placement import optimal_placement  # noqa: E402

app = FastAPI(title="CPS Testbed")
security = HTTPBasic(auto_error=False)
USER = os.environ.get("CPS_WEB_USER", "admin")
PASSWORD = os.environ.get("CPS_WEB_PASSWORD", "")


def auth(creds: Optional[HTTPBasicCredentials] = Depends(security)):
    if not PASSWORD:
        return
    ok = creds and secrets.compare_digest(creds.username, USER) and secrets.compare_digest(creds.password, PASSWORD)
    if not ok:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Basic"})


# ------------------------------------------------------------------ experiment queue
class RunRequest(BaseModel):
    case: str = Field("14", pattern=r"^(14|30|39|57|118|300)$")
    name: str = Field("web", pattern=r"^[A-Za-z0-9_-]{1,40}$")
    duration: float = Field(10, ge=1, le=60)
    grid_step: float = Field(0.5, ge=0.1, le=5)
    rate: float = Field(30, ge=1, le=120)
    solver: str = Field("gridpack", pattern=r"^(gridpack|builtin)$")
    placement: int = Field(1, ge=1, le=2)
    latency: float = Field(10, ge=0.1, le=2000)
    latency_spread: float = Field(0.5, ge=0, le=0.95)
    jitter: float = Field(2, ge=0, le=500)
    loss: float = Field(0, ge=0, le=0.9)
    pdc_wait: float = Field(20, ge=1, le=2000)
    attack: str = Field("none", pattern=r"^(none|fdi-simple|fdi-stealthy|drop|delay)$")
    target: Optional[int] = Field(None, ge=1, le=99999)
    fake: Optional[float] = Field(None, ge=0.5, le=1.5)
    attack_start: float = Field(3, ge=0, le=60)
    attack_end: float = Field(8, ge=0, le=60)
    attack_delay: float = Field(100, ge=0, le=5000)
    bdd: str = Field("on", pattern=r"^(on|off)$")
    control: str = Field("on", pattern=r"^(on|off)$")
    vmin: float = Field(0.94, ge=0.5, le=1.0)
    vmax: float = Field(1.08, ge=1.0, le=1.5)
    event: str = Field("none", pattern=r"^(none|avr:\d+:[0-9.]+:[0-9.]+|load:\d+:-?[0-9.]+:[0-9.]+)$")
    seed: int = Field(1, ge=1, le=10**6)

    def argv(self):
        a = []
        for k, v in self.model_dump().items():
            if v is None:
                continue
            a += [f"--{k.replace('_', '-')}", str(v)]
        return a


jobs = {}           # job id -> dict
job_queue = queue.Queue()
lock = threading.Lock()


def worker():
    while True:
        jid = job_queue.get()
        job = jobs[jid]
        job.update(status="running", started=time.time())
        log_path = os.path.join(RESULTS, f".job_{jid}.log")
        with open(log_path, "w") as log:
            p = subprocess.Popen([sys.executable, os.path.join(FED, "run_experiment.py")] + job["argv"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 text=True, cwd=FED)
            for line in p.stdout:
                log.write(line); log.flush()
                m = re.match(r"\[RUN\] (\S+):", line)
                if m:
                    job["run_id"] = m.group(1)
            code = p.wait()
        ok = code == 0 and job.get("run_id") and os.path.exists(os.path.join(RESULTS, job["run_id"], "summary.json"))
        job.update(status="done" if ok else "failed", finished=time.time(), log=log_path)


threading.Thread(target=worker, daemon=True).start()


# ------------------------------------------------------------------ helpers
def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def run_dir(run_id):
    if not re.match(r"^[0-9]{8}_[0-9]{6}_[A-Za-z0-9_-]+$", run_id):
        raise HTTPException(400, "bad run id")
    d = os.path.join(RESULTS, run_id)
    if not os.path.exists(os.path.join(d, "summary.json")):
        raise HTTPException(404, "run not found")
    return d


def thin(n, limit=600):
    return list(range(0, n, max(1, n // limit)))


# ------------------------------------------------------------------ API
@app.get("/", include_in_schema=False)
def index(_=Depends(auth)):
    return FileResponse(os.path.join(HERE, "index.html"))


_case_cache = {}


@app.get("/api/cases")
def cases(_=Depends(auth)):
    if not _case_cache:
        for c in ("14", "30", "39", "57", "118", "300"):
            topo = json.load(open(os.path.join(CASES, f"ieee{c}", "topology.json")))
            net = Network(topo)
            V, _, _ = net.solve_pf()
            _case_cache[c] = {
                "case": c, "buses": net.n, "branches": len(net.branches),
                "gens": sorted({g["bus"] for g in topo["gens"] if g["status"]}),
                "bus_ids": net.bus_ids,
                "pmus_min": len(optimal_placement(net, 1)[0]),
                "max_v_bus": net.bus_ids[int(np.argmax(np.abs(V)))], "max_v": round(float(np.abs(V).max()), 4)}
    return list(_case_cache.values())


@app.post("/api/runs")
def submit(req: RunRequest, _=Depends(auth)):
    if req.attack_end <= req.attack_start and req.attack != "none":
        raise HTTPException(422, "attack end must be after attack start")
    with lock:
        jid = secrets.token_hex(4)
        jobs[jid] = {"id": jid, "status": "queued", "request": req.model_dump(), "argv": req.argv(),
                     "submitted": time.time()}
    job_queue.put(jid)
    return jobs[jid]


@app.get("/api/jobs")
def list_jobs(_=Depends(auth)):
    out = []
    for j in sorted(jobs.values(), key=lambda x: -x["submitted"])[:20]:
        item = {k: v for k, v in j.items() if k not in ("argv", "log")}
        lp = j.get("log") or os.path.join(RESULTS, f".job_{j['id']}.log")
        if os.path.exists(lp):
            item["log_tail"] = open(lp).read()[-2000:]
        out.append(item)
    return out


@app.get("/api/runs")
def list_runs(_=Depends(auth)):
    runs = []
    for d in sorted(os.listdir(RESULTS), reverse=True):
        p = os.path.join(RESULTS, d, "summary.json")
        if not os.path.exists(p):
            continue
        s = json.load(open(p))
        meta = json.load(open(os.path.join(RESULTS, d, "meta.json")))
        a = meta["args"]
        runs.append({"id": d, "name": s["name"], "case": a["case"], "attack": a["attack"], "loss": a["loss"],
                     "latency": a["latency"], "bdd": a["bdd"], "control": a["control"], "placement": a["placement"],
                     "event": a["event"], "violation_s": s["grid"]["true_violation_time_s"],
                     "detection": s["attack"].get("detection_rate_pct"),
                     "delivery": s["network"]["delivery_ratio"]})
    return runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, _=Depends(auth)):
    d = run_dir(run_id)
    meta = json.load(open(os.path.join(d, "meta.json")))
    return {"id": run_id, "summary": json.load(open(os.path.join(d, "summary.json"))), "meta": meta,
            "commands": read_csv(os.path.join(d, "commands_applied.csv"))}


@app.get("/api/runs/{run_id}/series")
def series(run_id: str, bus: Optional[int] = None, _=Depends(auth)):
    d = run_dir(run_id)
    meta = json.load(open(os.path.join(d, "meta.json")))
    truth = read_csv(os.path.join(d, "grid_truth.csv"))
    est = read_csv(os.path.join(d, "cc_estimates.csv"))
    cc = read_csv(os.path.join(d, "cc_log.csv"))
    frames = read_csv(os.path.join(d, "frames.csv"))
    bus = bus or meta["target_bus"]
    col = f"v{bus}"
    if truth and col not in truth[0]:
        raise HTTPException(404, "bus not in this case")
    out = {"bus": bus, "vmax": meta["args"]["vmax"], "vmin": meta["args"]["vmin"],
           "attack_window": [meta["args"]["attack_start"], meta["args"]["attack_end"]] if meta["args"]["attack"] != "none" else None,
           "truth": [[float(r["t"]), float(r[col])] for r in truth],
           "truth_max": [[float(r["t"]), max(float(v) for k, v in r.items() if k != "t")] for r in truth]}
    idx = thin(len(est))
    out["estimate"] = [[float(est[i]["t"]), float(est[i][col])] for i in idx]
    idx = thin(len(cc))
    out["chi2"] = [[float(cc[i]["t"]), float(cc[i]["first_J"]) if "first_J" in cc[i] else float(cc[i]["J"]),
                    float(cc[i]["threshold"]), int(cc[i]["first_alarm"])] for i in idx]
    out["est_max"] = [[float(cc[i]["t"]), float(cc[i]["max_v_est"])] for i in idx]
    out["completeness"] = [[float(cc[i]["t"]), int(cc[i]["pmus_received"]) / max(int(cc[i]["pmus_expected"]), 1)] for i in idx]
    lat = [float(f["latency_ms"]) for f in frames if f["status"] == "delivered"]
    if lat:
        hist, edges = np.histogram(lat, bins=30)
        out["latency_hist"] = [[round(float((edges[i] + edges[i + 1]) / 2), 2), int(hist[i])] for i in range(len(hist))]
    per = {}
    for f in frames:
        b = f["bus"]; per.setdefault(b, [0, 0, 0])
        per[b][1] += 1
        if f["status"] == "delivered":
            per[b][0] += 1
        if f["attacked"] == "1":
            per[b][2] += 1
    out["pmus"] = [{"bus": int(b), "delivery": round(v[0] / v[1], 3), "attacked_frames": v[2]}
                   for b, v in sorted(per.items(), key=lambda x: int(x[0]))]
    return out
