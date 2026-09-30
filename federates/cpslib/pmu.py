"""PMU channel layout and the linear phasor measurement model.

A PMU at bus i reports channel 0 = voltage phasor V_i, then one current phasor for
every in-service branch incident to i (the current leaving bus i on that branch).
With all quantities complex, the measurements are linear in the bus voltages:

    z = H V,   H rows = unit vector (voltage) or a row of Yf / Yt (current)
"""
import numpy as np


class PmuLayout:
    def __init__(self, net, pmu_buses):
        self.net = net
        self.pmus = []          # [{"bus": b, "id": k, "channels": [(kind, branch_idx, end)]}]
        rows = []
        for k, b in enumerate(pmu_buses):
            i = net.idx[b]
            ch = [("V", -1, "")]
            rows.append(np.eye(net.n)[i].astype(complex))
            for br, (f, t) in enumerate(zip(net.f, net.t)):
                if f == i:
                    ch.append(("I", br, "from")); rows.append(net.Yf[br])
                elif t == i:
                    ch.append(("I", br, "to")); rows.append(net.Yt[br])
            self.pmus.append({"bus": b, "id": k + 1, "channels": ch})
        self.H = np.array(rows)
        # (pmu index, channel index) -> row of H
        self.row = {}
        r = 0
        for p, pm in enumerate(self.pmus):
            for c in range(len(pm["channels"])):
                self.row[(p, c)] = r; r += 1

    def measure(self, V):
        """Noise-free phasors per PMU, as nested lists [[re, im], ...]."""
        z = self.H @ V
        out, r = [], 0
        for pm in self.pmus:
            m = len(pm["channels"])
            out.append([[float(x.real), float(x.imag)] for x in z[r:r + m]])
            r += m
        return out

    def channel_names(self, p):
        pm, net = self.pmus[p], self.net
        names = []
        for kind, br, end in pm["channels"]:
            if kind == "V":
                names.append(f"V{pm['bus']}")
            else:
                f, t = net.bus_ids[net.f[br]], net.bus_ids[net.t[br]]
                names.append(f"I{f}-{t}" if end == "from" else f"I{t}-{f}")
        return names

    def describe(self):
        return [{"bus": pm["bus"], "id": pm["id"], "channels": self.channel_names(p)}
                for p, pm in enumerate(self.pmus)]
