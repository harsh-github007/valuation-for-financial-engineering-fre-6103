"""CDO valuation with the Lintner (certainty-equivalent CAPM) method -- FRE 6103 Mini-Project 3, Part 2.

Reuses the Part 1 model (cdo_simulation.py): the same 1,000 fixed, moment-matched cases, the same
correlated exponential default dates, BIS bond cash flows and the same quarterly waterfall.

    python cdo_valuation.py            # base case, prints every number in the paper
"""
from __future__ import annotations

import json
import os
from dataclasses import replace

import numpy as np

from cdo_simulation import (Params, bond_cashflows, default_times, fixed_normals, promised_bond,
                            promised_collateral, promised_tranche, waterfall)

# Part 2 inputs (assignment): A $15 MM at 4.5%, B $30 MM at 5.5%, risk-free 4% p.a.
BASE = replace(Params(), a_notional=15.0, a_coupon=0.045, b_notional=30.0, b_coupon=0.055, rf=0.04)
TOL = 1e-9


# ---------------------------------------------------------------- step 1: scheduled waterfall
def scheduled(p: Params):
    """Promised (no-default) cash flows by quarter for the collateral and each class."""
    C = promised_collateral(p)
    PA = promised_tranche(p.a_notional, p.a_coupon, p.maturity_q)
    PB = promised_tranche(p.b_notional, p.b_coupon, p.maturity_q)
    return C, PA, PB, C - PA - PB


def disc(p: Params, rate: float) -> np.ndarray:
    """Quarterly discount factors (1 + r/4)^-k, k = 1..20."""
    return (1 + rate / p.freq) ** -np.arange(1, p.maturity_q + 1)


def bond_price(p: Params) -> float:
    """Market price of one collateral bond: promised cash flows discounted at the 9% YTM."""
    return float(promised_bond(p) @ disc(p, p.ytm))


# ---------------------------------------------------------------- steps 2-5
def simulate(p: Params, z_mm):
    """Step 2: 1,000 cases of collateral cash (static random numbers from Part 1)."""
    tau = default_times(p, z_mm)
    CF = bond_cashflows(p, tau)
    return tau, CF, CF.sum(axis=1)


def lintner(p: Params, C: np.ndarray, CF: np.ndarray | None = None):
    """Steps 3-5 for one structure, given collateral cash C (cases x quarters)."""
    A, B, E, PA, PB = waterfall(p, C)
    d = disc(p, p.rf)
    X = np.column_stack([A @ d, B @ d, E @ d])           # PV at rf of each class, each case
    M = X.sum(axis=1)                                    # PV of the whole pool (the "market")
    cov = np.cov(X, rowvar=False, bias=True)             # 3x3 covariance (divide by N, as in moment matching)
    cov_M = cov.sum(axis=1)                              # Cov(class, pool) = row sums
    varM = cov.sum()

    P_M = p.n_bonds * bond_price(p)                      # market value of collateral
    EM = M.mean()
    cost_of_risk = EM - P_M                              # step 4: implicit cost of risk
    lam = cost_of_risk / varM                            # cost per unit risk ($ per $^2)

    EV = X.mean(axis=0)
    V = EV - lam * cov_M                                 # step 5: Lintner value
    dflt = {"A": (PA - A > TOL).any(axis=1), "B": (PB - B > TOL).any(axis=1)}   # default indicators
    out = dict(EV=EV, V=V, cov=cov, cov_M=cov_M, varM=varM, P_M=P_M, EM=EM, cost=cost_of_risk, lam=lam,
               risk_charge=lam * cov_M, PD_A=float(dflt["A"].mean()), PD_B=float(dflt["B"].mean()),
               X=X, A=A, B=B, E=E, PA=PA, PB=PB, dflt=dflt)
    if CF is not None:                                   # same price of risk recovered bond by bond
        Xb = CF @ d                                      # cases x bonds
        cost_b = Xb.mean(0) - bond_price(p)
        cov_bM = ((Xb - Xb.mean(0)) * (M - EM)[:, None]).mean(0)
        out["lam_by_bond"] = cost_b / cov_bM
    return out


def irr(cf: np.ndarray, price: float, freq=4) -> float:
    """Annual rate (quarterly compounding) at which cash flows cf are worth price."""
    k = np.arange(1, len(cf) + 1)
    lo, hi = -0.5, 2.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cf @ (1 + mid / freq) ** -k > price else (lo, mid)
    return (lo + hi) / 2


def fair_coupon(p: Params, C, cls="B") -> float:
    """Coupon at which the class's Lintner value equals its notional (par)."""
    lo, hi = 0.0, 0.40
    idx, key = (0, "a_coupon") if cls == "A" else (1, "b_coupon")
    N = p.a_notional if cls == "A" else p.b_notional
    for _ in range(60):
        mid = (lo + hi) / 2
        v = lintner(replace(p, **{key: mid}), C)["V"][idx]
        lo, hi = (mid, hi) if v < N else (lo, mid)
    return (lo + hi) / 2


# ---------------------------------------------------------------- step 6 (bonus)
def structure_scan(p: Params, C, grid):
    """Bank buys the collateral at market, sells A and B at par at their target coupons, keeps the residual.
    Gain to the residual holder = V_E - (P_M - N_A - N_B) = (N_A - V_A) + (N_B - V_B)."""
    rows = []
    for nb in grid:
        r = lintner(replace(p, b_notional=float(nb)), C)
        cost_E = r["P_M"] - p.a_notional - nb
        rows.append(dict(N_B=float(nb), V_A=r["V"][0], V_B=r["V"][1], V_E=r["V"][2], equity_cost=cost_E,
                         gain=r["V"][2] - cost_E, PD_A=r["PD_A"], PD_B=r["PD_B"]))
    return rows


def optimise(rows, cap):
    feas = [r for r in rows if r["PD_B"] <= cap + 1e-12 and r["PD_A"] == 0]
    return max(feas, key=lambda r: r["gain"])


def checks(p, z_mm, r, CF):
    assert np.allclose(r["V"].sum(), r["P_M"], atol=1e-8), "class values must add to the collateral price"
    assert np.allclose(r["X"].sum(1), CF.sum(1) @ disc(p, p.rf))   # every dollar of pool cash is allocated
    assert np.allclose(r["lam_by_bond"].mean(), r["lam"], rtol=0.05)
    zero = replace(p, pd_annual=0.0)
    rz = lintner(zero, bond_cashflows(zero, default_times(zero, z_mm)).sum(1))
    assert np.allclose(rz["cov"], 0, atol=1e-12)           # no defaults -> no risk
    riskless = promised_tranche(p.a_notional, p.a_coupon, p.maturity_q) @ disc(p, p.rf)
    assert np.isclose(r["V"][0], riskless) == (r["PD_A"] == 0)  # A never short -> worth riskless PV


# ---------------------------------------------------------------- charts
BLUE, ORANGE, GREEN, GREY, RED = "#2a78d6", "#eb6834", "#1baf7a", "#52514e", "#c23b3b"


def make_charts(p, sched, r, rows, sens, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .3, "axes.titleweight": "bold",
                         "axes.titlelocation": "left", "axes.axisbelow": True})
    d = f"{outdir}/charts"
    os.makedirs(d, exist_ok=True)
    saved = []

    def save(fig, name):
        fig.tight_layout(); fig.savefig(f"{d}/{name}"); plt.close(fig); saved.append(name)

    C, PA, PB, PE = sched
    q = np.arange(1, p.maturity_q)
    kw = dict(width=.75, edgecolor="white", linewidth=.8)
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.bar(q, PA[:-1], color=BLUE, label=f"Class A (${PA[0]:.4f}M)", **kw)
    ax.bar(q, PB[:-1], bottom=PA[:-1], color=ORANGE, label=f"Class B (${PB[0]:.4f}M)", **kw)
    ax.bar(q, PE[:-1], bottom=PA[:-1] + PB[:-1], color=GREEN, label=f"Residual (${PE[0]:.4f}M)", **kw)
    ax.set(title=f"Scheduled waterfall, Q1-19 (Q20: A ${PA[-1]:.2f}M, B ${PB[-1]:.2f}M, residual ${PE[-1]:.2f}M)",
           xlabel="quarter", ylabel="$M", xticks=range(1, p.maturity_q, 2), ylim=(0, 1.85))
    ax.title.set_fontsize(9.5)
    ax.legend(ncol=3, loc="upper right", fontsize=8)
    ax.grid(axis="x", visible=False)
    save(fig, "01_scheduled_waterfall.png")

    X = r["X"]
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.2))
    for ax, i, name, col in zip(axs, range(3), ["Class A", "Class B", "Residual"], [BLUE, ORANGE, GREEN]):
        x = X[:, i]
        if np.ptp(x) < 1e-9:
            ax.bar([x[0]], [100], width=1.0, color=col)
            ax.set_xlim(x[0] - 4, x[0] + 4); ax.set_ylim(0, 135)
            ax.text(x[0], 104, f"${x[0]:.2f}M in every case", ha="center", fontsize=9)
        else:
            ax.hist(x, bins=30, color=col, edgecolor="white", weights=np.full(len(x), 100 / len(x)))
            ax.axvline(r["EV"][i], color=GREY, ls="--", lw=1)
            ax.axvline(r["V"][i], color=RED, ls="-", lw=1.2)
            ax.text(r["EV"][i], ax.get_ylim()[1] * .92, f"E[PV] {r['EV'][i]:.1f} ", fontsize=8, color=GREY, ha="right")
            ax.text(r["V"][i], ax.get_ylim()[1] * .70, f"Lintner {r['V'][i]:.1f} ", fontsize=8, color=RED, ha="right")
        ax.set(title=f"{name}: PV at 4%", xlabel="$M", ylabel="% of cases" if i == 0 else None)
    save(fig, "02_pv_distributions.png")

    fig, ax = plt.subplots(figsize=(8, 3.4))
    names = ["Class A", "Class B", "Residual", "Collateral"]
    ev = list(r["EV"]) + [r["EM"]]
    v = list(r["V"]) + [r["P_M"]]
    x = np.arange(4)
    ax.bar(x - .18, ev, width=.36, color=GREY, alpha=.45, label="expected PV at risk-free rate")
    ax.bar(x + .18, v, width=.36, color=[BLUE, ORANGE, GREEN, "#6b5bd6"], label="Lintner value")
    for xi, a, b in zip(x, ev, v):
        ax.text(xi + .18, b + 1.2, f"{b:.2f}", ha="center", fontsize=8)
        if a - b > .05: ax.text(xi - .18, a + 1.2, f"-{a - b:.2f}", ha="center", fontsize=8, color=RED)
    ax.set_xticks(x, names)
    ax.set(title="Expected PV less the risk charge = Lintner value ($M)", ylabel="$M", ylim=(0, 112))
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="x", visible=False)
    save(fig, "03_value_bridge.png")

    nb = np.array([w["N_B"] for w in rows])
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(nb, [w["gain"] for w in rows], color=GREEN, lw=2, label="gain to residual holder ($M, left)")
    ax.axhline(0, color=GREY, lw=.8)
    ax.axvline(p.b_notional, color=GREY, ls=":", lw=1)
    ax.text(p.b_notional, -1.2, r" assignment: B = \$30M", fontsize=8, color=GREY)
    ax.set(xlabel=r"Class B principal (\$M), A fixed at \$15M", ylabel="$M",
           title="Bonus: value created for the residual vs Class B size")
    ax2 = ax.twinx()
    ax2.step(nb, [w["PD_B"] * 100 for w in rows], where="post", color=ORANGE, lw=1.4, label="Class B default prob. (%, right)")
    ax2.set_ylabel("%"); ax2.grid(False); ax2.spines["right"].set_visible(True)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")
    save(fig, "04_structure_scan.png")

    fig, ax = plt.subplots(figsize=(8, 3.4))
    rhos = [s["rho"] for s in sens]
    for k, name, col in [("V_B", "Class B", ORANGE), ("V_E", "Residual", GREEN)]:
        ax.plot(rhos, [s[k] for s in sens], "o-", color=col, label=name)
    ax.set(title="Lintner values as correlation changes (A $15M / B $45M)", xlabel="correlation of normals", ylabel="$M")
    ax.legend(fontsize=8)
    save(fig, "05_correlation.png")
    return saved


# ---------------------------------------------------------------- main
def main(outdir="results_part2"):
    os.makedirs(outdir, exist_ok=True)
    p = BASE
    z_mm = fixed_normals(p)
    tau, CF, C = simulate(p, z_mm)
    sched = scheduled(p)
    r = lintner(p, C, CF)
    checks(p, z_mm, r, CF)

    res = {"inputs": {k: getattr(p, k) for k in ("a_notional", "a_coupon", "b_notional", "b_coupon", "rf", "ytm",
                                                 "pd_annual", "lgd", "rho", "n_cases", "seed")}}
    res["bond_price_per_10MM"] = bond_price(p)
    res["bond_price_pct_par"] = bond_price(p) / p.face * 100
    keys = ("P_M", "EM", "cost", "lam", "varM", "PD_A", "PD_B")
    res.update({k: float(r[k]) for k in keys})
    res["lam_by_bond_min_max"] = [float(r["lam_by_bond"].min()), float(r["lam_by_bond"].max())]
    res["cov"] = r["cov"].tolist()
    names = ["A", "B", "E"]
    sched_pv = [sched[1] @ disc(p, p.rf), sched[2] @ disc(p, p.rf), sched[3] @ disc(p, p.rf)]
    tr = {}
    for i, n in enumerate(names):
        exp_cf = [r["A"], r["B"], r["E"]][i].mean(0)
        prom = sched[1:][i]
        tr[n] = dict(scheduled_PV_rf=float(sched_pv[i]), E_PV=float(r["EV"][i]), std_PV=float(np.sqrt(r["cov"][i, i])),
                     cov_with_pool=float(r["cov_M"][i]), risk_charge=float(r["risk_charge"][i]), V=float(r["V"][i]),
                     exp_return=irr(exp_cf, r["V"][i]), promised_yield=irr(prom, r["V"][i]),
                     beta=float(r["cov_M"][i] / r["varM"]))
    tr["A"]["notional"], tr["B"]["notional"] = p.a_notional, p.b_notional
    tr["E"]["notional"] = r["P_M"] - p.a_notional - p.b_notional
    res["tranches"] = tr
    res["pool_exp_return"] = irr(CF.sum(1).mean(0), r["P_M"])
    res["fair_coupon_B"] = fair_coupon(p, C, "B")

    # bonus
    # B can grow until the notes raise the full cost of the collateral (residual investment >= 0)
    grid = np.round(np.arange(0, bond_price(p) * p.n_bonds - p.a_notional + 1e-9, 0.25), 2)
    rows = structure_scan(p, C, grid)
    caps = [0.0, 0.01, 0.02, 0.05, 0.10, 0.20, 0.35]
    res["optimum_by_cap"] = [dict(cap=c, **optimise(rows, c)) for c in caps]
    res["breakeven_NB"] = next(w["N_B"] for w in rows if w["N_B"] > p.b_notional and w["gain"] > 0)
    # largest B that Class B investors would still buy at par in Lintner terms (V_B >= N_B)
    res["max_NB_fair"] = max(w["N_B"] for w in rows if w["V_B"] >= w["N_B"] - 1e-9)
    res["assignment_structure"] = next(w for w in rows if w["N_B"] == p.b_notional)

    # alternative parameter (assignment PS): B = $45 MM, so that Class B actually carries some risk
    ra = lintner(replace(p, b_notional=45.0), C)
    res["alt_B45"] = dict(cov=ra["cov"].tolist(), EV=ra["EV"].tolist(), V=ra["V"].tolist(),
                          risk_charge=ra["risk_charge"].tolist(), beta=(ra["cov_M"] / ra["varM"]).tolist(),
                          PD_A=ra["PD_A"], PD_B=ra["PD_B"], lam=float(ra["lam"]),
                          exp_return=[irr(x.mean(0), v) for x, v in zip((ra["A"], ra["B"], ra["E"]), ra["V"])],
                          fair_coupon_B=fair_coupon(replace(p, b_notional=45.0), C, "B"))

    # sensitivity of values to correlation for a structure where B is actually risky
    sens = []
    for rho in (0.0, 0.1, 0.2, 0.4, 0.6, 0.8):
        q_ = replace(p, rho=rho, b_notional=45.0)
        _, CFr, Cr = simulate(q_, z_mm)
        rr = lintner(q_, Cr)
        sens.append(dict(rho=rho, lam=float(rr["lam"]), V_A=float(rr["V"][0]), V_B=float(rr["V"][1]),
                         V_E=float(rr["V"][2]), PD_B=rr["PD_B"], EV_E=float(rr["EV"][2])))
    res["correlation_sensitivity_B45"] = sens

    # files
    qtr = np.arange(1, p.maturity_q + 1)
    np.savetxt(f"{outdir}/scheduled_waterfall.csv", np.column_stack([qtr, *sched]), delimiter=",",
               header="quarter,collateral,A,B,residual", comments="", fmt=["%d"] + ["%.6f"] * 4)
    ids = np.arange(1, p.n_cases + 1)
    np.savetxt(f"{outdir}/case_pv_and_defaults.csv",
               np.column_stack([ids, r["X"], r["X"].sum(1), r["dflt"]["A"], r["dflt"]["B"]]), delimiter=",",
               header="case,PV_A,PV_B,PV_residual,PV_pool,default_A,default_B", comments="",
               fmt=["%d"] + ["%.6f"] * 4 + ["%d", "%d"])
    with open(f"{outdir}/structure_scan.csv", "w") as fh:
        fh.write(",".join(rows[0]) + "\n")
        for w in rows:
            fh.write(",".join(f"{v:.6f}" for v in w.values()) + "\n")
    try:
        res["charts"] = make_charts(p, sched, r, rows, sens, outdir)
    except ImportError:
        res["charts"] = "matplotlib not installed"
    with open(f"{outdir}/results.json", "w") as f:
        json.dump(res, f, indent=2, default=float)
    return res, sched, r


if __name__ == "__main__":
    res, sched, r = main()
    np.set_printoptions(suppress=True, linewidth=120)
    print("All checks passed.\n")
    print("Scheduled waterfall ($MM) - quarter 1 and quarter 20:")
    print("  collateral, A, B, residual  Q1:", np.round([s[0] for s in sched], 5), " Q20:", np.round([s[-1] for s in sched], 5))
    print(f"\nBond price at 9% YTM: {res['bond_price_per_10MM']:.4f} per $10MM ({res['bond_price_pct_par']:.2f}% of par)")
    print(f"Collateral market value P_M = {res['P_M']:.4f}; E[PV at 4%] = {res['EM']:.4f}")
    print(f"Cost of risk = {res['cost']:.4f}; Var(PV pool) = {res['varM']:.4f}; lambda = {res['lam']:.6f} per $MM^2")
    print("lambda recovered bond by bond: min/max", np.round(res["lam_by_bond_min_max"], 6))
    print("\nCovariance matrix of PVs (A, B, residual):\n", np.round(r["cov"], 4))
    print(f"P(A default) = {res['PD_A']:.3%}, P(B default) = {res['PD_B']:.3%}")
    for n, t in res["tranches"].items():
        print(n, {k: round(v, 5) for k, v in t.items()})
    print(f"pool expected return {res['pool_exp_return']:.4%}; fair coupon B {res['fair_coupon_B']:.4%}")
    print("\nAssignment structure:", {k: round(v, 4) for k, v in res["assignment_structure"].items()})
    print(f"Break-even B size {res['breakeven_NB']}; largest B worth >= par {res['max_NB_fair']}")
    for o in res["optimum_by_cap"]:
        print({k: round(v, 4) for k, v in o.items()})
    print("\nAlternative B=$45M:", json.dumps(res["alt_B45"], default=float, indent=1))
    print("\nCorrelation sensitivity (B = $45M):")
    for s in res["correlation_sensitivity_B45"]:
        print({k: round(v, 4) for k, v in s.items()})
