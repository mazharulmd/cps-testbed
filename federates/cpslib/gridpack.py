"""Run GridPACK's power-flow application (pf.x) on a network and read back the solution."""
import csv, os, shutil, subprocess
import numpy as np

from .rawio import write_raw

PF_EXE = os.environ.get("GRIDPACK_PF", "/home/ubuntu/software/GridPACK_install/bin/pf.x")
INPUT_XML = """<?xml version="1.0" encoding="utf-8"?>
<Configuration>
  <Powerflow>
    <networkConfiguration> case.raw </networkConfiguration>
    <maxIteration>50</maxIteration>
    <tolerance>1.0e-6</tolerance>
    <qlim>false</qlim>
    <outputFormat>csv</outputFormat>
    <outputFile>pf_out</outputFile>
    <LinearSolver>
      <PETScOptions>
        -ksp_type richardson
        -pc_type lu
        -pc_factor_mat_solver_type superlu_dist
        -ksp_max_it 1
      </PETScOptions>
    </LinearSolver>
  </Powerflow>
</Configuration>
"""


def available():
    return os.path.exists(PF_EXE) and shutil.which("mpirun") is not None


class GridPackSolver:
    """Writes the current operating point to a .raw file, runs pf.x, returns bus voltages."""

    def __init__(self, net, topo, workdir):
        self.net, self.topo, self.dir = net, topo, workdir
        os.makedirs(workdir, exist_ok=True)
        with open(os.path.join(workdir, "input.xml"), "w") as fh:
            fh.write(INPUT_XML)

    def solve(self, pd, qd, vset):
        write_raw(os.path.join(self.dir, "case.raw"), self.topo, pd, qd, vset)
        for f in ("pf_out_buses.csv", "pf_out_convergence.csv"):
            try:
                os.remove(os.path.join(self.dir, f))
            except FileNotFoundError:
                pass
        cmd = ["mpirun", "--allow-run-as-root", "--oversubscribe", "-np", "1", PF_EXE, "input.xml"]
        proc = subprocess.run(cmd, cwd=self.dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with open(os.path.join(self.dir, "pf.log"), "w") as fh:
            fh.write(proc.stdout)
        conv = os.path.join(self.dir, "pf_out_convergence.csv")
        buses = os.path.join(self.dir, "pf_out_buses.csv")
        if proc.returncode != 0 or not os.path.exists(conv) or not os.path.exists(buses):
            return None, 0, False
        with open(conv) as fh:
            c = next(csv.DictReader(fh))
        ok = c["converged"].strip().lower() == "true"
        V = np.zeros(self.net.n, complex)
        with open(buses) as fh:
            for row in csv.DictReader(fh):
                i = self.net.idx[int(row["bus_id"])]
                V[i] = float(row["voltage_pu"]) * np.exp(1j * np.deg2rad(float(row["angle_deg"])))
        return V, int(c["iterations"]), ok
