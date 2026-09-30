"""Linear PMU state estimation with chi-square bad data detection.

With PMU phasors the measurement model is linear, z = H V + e, so the weighted
least-squares estimate is V = (H^H W H)^-1 H^H W z. The residual objective
J = sum |r_k|^2 / sigma_k^2 follows a chi-square distribution with
2m - 2n degrees of freedom when the data are clean; J above the threshold flags
bad (possibly falsified) data. The largest normalized residual points to the
suspicious channel.
"""
import numpy as np
from scipy.stats import chi2


class StateEstimator:
    def __init__(self, layout, sigma=0.002, alpha=0.01, pseudo_sigma=0.05):
        self.L = layout
        self.sigma = sigma              # relative std-dev of a PMU phasor (rectangular)
        self.alpha = alpha              # false-alarm probability of the chi-square test
        self.pseudo_sigma = pseudo_sigma
        self.last = np.ones(layout.net.n, complex)

    def estimate(self, meas, exclude=()):
        """meas: {(pmu_idx, ch_idx): complex}. Returns dict with estimate and test results."""
        net = self.L.net
        keys = [k for k in meas if k not in exclude]
        rows = [self.L.row[k] for k in keys]
        H = self.L.H[rows] if rows else np.zeros((0, net.n), complex)
        z = np.array([meas[k] for k in keys], complex)
        sig = np.maximum(self.sigma * np.abs(z), 1e-4)
        W = 1.0 / sig ** 2
        G = (H.conj().T * W) @ H
        # rank with NumPy's relative tolerance (G entries are ~1/sigma^2)
        observable = len(rows) >= net.n and np.linalg.matrix_rank(G) == net.n
        rhs = (H.conj().T * W) @ z
        V = None
        if observable:
            try:
                V = np.linalg.solve(G, rhs)
            except np.linalg.LinAlgError:
                observable = False
        pseudo = 0
        if not observable:
            # keep the estimator solvable with weak pseudo-measurements from the last estimate
            G = G + np.eye(net.n) / self.pseudo_sigma ** 2
            rhs = rhs + self.last / self.pseudo_sigma ** 2
            pseudo = net.n
            V = np.linalg.solve(G, rhs)
        r = z - H @ V
        J = float(np.sum(np.abs(r) ** 2 * W))
        dof = max(2 * len(rows) - 2 * net.n, 1) if observable else max(2 * len(rows), 1)
        thr = float(chi2.ppf(1 - self.alpha, dof))
        # normalized residuals: r_k / sqrt(Omega_kk), Omega = R - H G^-1 H^H
        worst = None
        if observable and len(rows) > net.n:
            Ginv = np.linalg.inv(G)
            omega = sig ** 2 - np.real(np.einsum("ij,jk,ik->i", H, Ginv, H.conj()))
            rn = np.abs(r) / np.sqrt(np.maximum(omega, 1e-12))
            k = int(np.argmax(rn))
            worst = (keys[k], float(rn[k]))
        self.last = V
        return {"V": V, "J": J, "threshold": thr, "dof": dof, "alarm": bool(observable and J > thr),
                "observable": bool(observable), "m": len(rows), "worst": worst}

    def estimate_with_bdd(self, meas, max_removals=3):
        """Run the chi-square test; on an alarm remove the PMU with the largest normalized
        residual and re-estimate, up to max_removals PMUs."""
        removed, excl = [], set()
        res = self.estimate(meas)
        first = res
        while res["alarm"] and res["worst"] and len(removed) < max_removals:
            p = res["worst"][0][0]
            removed.append(p)
            excl |= {k for k in meas if k[0] == p}
            res = self.estimate(meas, exclude=excl)
        res["removed_pmus"] = removed
        res["first_J"], res["first_alarm"] = first["J"], first["alarm"]
        return res
