"""Network model built from cases/<name>/topology.json (MATPOWER conventions)."""
import json
import numpy as np


class Network:
    def __init__(self, topo):
        if isinstance(topo, str):
            with open(topo) as fh:
                topo = json.load(fh)
        self.base = topo["baseMVA"]
        self.buses = topo["buses"]
        self.gens = topo["gens"]
        self.branches = [b for b in topo["branches"] if b["status"]]
        self.bus_ids = [b["id"] for b in self.buses]
        self.idx = {b: i for i, b in enumerate(self.bus_ids)}
        self.n = len(self.bus_ids)
        self._build_admittances()

    def _build_admittances(self):
        """Branch admittances in MATPOWER form: If = Yf V, It = Yt V, Ybus = Cf'Yf + Ct'Yt + diag(Ysh)."""
        nl, n = len(self.branches), self.n
        Ytt = np.zeros(nl, complex); Yff = np.zeros(nl, complex)
        Yft = np.zeros(nl, complex); Ytf = np.zeros(nl, complex)
        f = np.zeros(nl, int); t = np.zeros(nl, int)
        for k, br in enumerate(self.branches):
            ys = 1.0 / complex(br["r"], br["x"])
            bc = br["b"]
            tap = br["tap"] if br["tap"] else 1.0
            tap = tap * np.exp(1j * np.deg2rad(br["shift"]))
            Ytt[k] = ys + 1j * bc / 2
            Yff[k] = Ytt[k] / (tap * np.conj(tap))
            Yft[k] = -ys / np.conj(tap)
            Ytf[k] = -ys / tap
            f[k], t[k] = self.idx[br["from"]], self.idx[br["to"]]
        self.f, self.t = f, t
        self.Yf = np.zeros((nl, n), complex); self.Yt = np.zeros((nl, n), complex)
        self.Yf[np.arange(nl), f] = Yff; self.Yf[np.arange(nl), t] = Yft
        self.Yt[np.arange(nl), f] = Ytf; self.Yt[np.arange(nl), t] = Ytt
        ysh = np.array([complex(b["gs"], b["bs"]) / self.base for b in self.buses])
        Cf = np.zeros((nl, n)); Cf[np.arange(nl), f] = 1
        Ct = np.zeros((nl, n)); Ct[np.arange(nl), t] = 1
        self.Ybus = Cf.T @ self.Yf + Ct.T @ self.Yt + np.diag(ysh)

    def adjacency(self):
        """Bus-to-bus connectivity matrix including self connections (for PMU placement)."""
        A = np.eye(self.n, dtype=int)
        A[self.f, self.t] = 1; A[self.t, self.f] = 1
        return A

    def solve_pf(self, pd=None, qd=None, vset=None, tol=1e-9, max_it=30):
        """Newton-Raphson power flow (reference solver; loads in MW/MVAr, vset {bus_id: pu})."""
        n, base = self.n, self.base
        pd = np.array([b["pd"] for b in self.buses]) if pd is None else np.asarray(pd, float)
        qd = np.array([b["qd"] for b in self.buses]) if qd is None else np.asarray(qd, float)
        types = np.array([b["type"] for b in self.buses])
        pg = np.zeros(n); V0 = np.ones(n)
        for g in self.gens:
            if g["status"]:
                i = self.idx[g["bus"]]
                pg[i] += g["pg"]; V0[i] = g["vg"]
        if vset:
            for b, v in vset.items():
                V0[self.idx[b]] = v
        # buses whose generators are all off become PQ
        has_gen = np.zeros(n, bool)
        for g in self.gens:
            if g["status"]:
                has_gen[self.idx[g["bus"]]] = True
        types = np.where((types == 2) & ~has_gen, 1, types)
        ref = np.where(types == 3)[0]; pv = np.where(types == 2)[0]; pq = np.where(types == 1)[0]
        Sbus = (pg - pd - 1j * qd) / base
        V = V0.astype(complex)
        pvpq = np.r_[pv, pq]
        for it in range(max_it):
            mis = V * np.conj(self.Ybus @ V) - Sbus
            F = np.r_[mis[pvpq].real, mis[pq].imag]
            if np.max(np.abs(F)) < tol:
                return V, it, True
            Ibus = self.Ybus @ V
            dS_dVm = np.diag(V) @ np.conj(self.Ybus @ np.diag(V / np.abs(V))) + np.diag(np.conj(Ibus) * V / np.abs(V))
            dS_dVa = 1j * np.diag(V) @ np.conj(np.diag(Ibus) - self.Ybus @ np.diag(V))
            J = np.block([[dS_dVa[np.ix_(pvpq, pvpq)].real, dS_dVm[np.ix_(pvpq, pq)].real],
                          [dS_dVa[np.ix_(pq, pvpq)].imag, dS_dVm[np.ix_(pq, pq)].imag]])
            dx = np.linalg.solve(J, -F)
            Va = np.angle(V); Vm = np.abs(V)
            Va[pvpq] += dx[:len(pvpq)]; Vm[pq] += dx[len(pvpq):]
            V = Vm * np.exp(1j * Va)
        return V, max_it, False
