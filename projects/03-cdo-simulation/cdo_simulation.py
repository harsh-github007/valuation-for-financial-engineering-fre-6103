from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, replace
from statistics import NormalDist

import numpy as np


@dataclass(frozen=True)
class Params:
    n_bonds: int = 10
    face: float = 10.0
    coupon: float = 0.06
    maturity_q: int = 20
    pd_annual: float = 0.04
    lgd: float = 0.60
    rho: float = 0.20
    ytm: float = 0.09
    rf: float = 0.01
    a_notional: float = 20.0
    a_coupon: float = 0.02
    b_notional: float = 10.0
    b_coupon: float = 0.04
    n_cases: int = 1000
    seed: int = 61032026
    freq: int = 4
    recovery: str = "bis"
    amort: str = "bullet"
    hazard: str = "conditional"


def fixed_normals(p: Params) -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(p.seed))
    u = rng.random((p.n_cases, p.n_bonds))
    z = np.vectorize(NormalDist().inv_cdf)(u)
    zc = z - z.mean(axis=0)
    L_sample = np.linalg.cholesky(zc.T @ zc / p.n_cases)
    return np.linalg.solve(L_sample, zc.T).T


def default_times(p: Params, z_mm: np.ndarray) -> np.ndarray:
    target = np.full((p.n_bonds, p.n_bonds), p.rho)
    np.fill_diagonal(target, 1.0)
    z_corr = z_mm @ np.linalg.cholesky(target).T
    u = np.clip(np.vectorize(NormalDist().cdf)(z_corr), 1e-12, 1 - 1e-12)
    if p.pd_annual == 0:
        return np.full_like(u, np.inf)
    if p.hazard == "rate":
        return -np.log(u) / p.pd_annual
    return np.log(u) / np.log(1.0 - p.pd_annual)


def default_date_correlation(p: Params, z_mm) -> float:
    c = np.corrcoef(default_times(p, z_mm), rowvar=False)
    return float(c[np.triu_indices(p.n_bonds, 1)].mean())


def calibrate_rho(p: Params, z_mm, target=0.20) -> float:
    lo, hi = 0.0, 0.99
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if default_date_correlation(replace(p, rho=mid), z_mm) < target else (lo, mid)
    return (lo + hi) / 2


def promised_bond(p: Params) -> np.ndarray:
    cf = np.full(p.maturity_q, p.face * p.coupon / p.freq)
    cf[-1] += p.face
    return cf


def bond_cashflows(p: Params, tau: np.ndarray) -> np.ndarray:
    t = np.arange(1, p.maturity_q + 1) / p.freq
    defaulted = tau[:, :, None] <= t
    if p.recovery == "par":
        default_now = defaulted & (tau[:, :, None] > t - 1.0 / p.freq)
        return promised_bond(p) * ~defaulted + (1.0 - p.lgd) * p.face * default_now
    return promised_bond(p) * np.where(defaulted, 1.0 - p.lgd, 1.0)


def promised_collateral(p: Params) -> np.ndarray:
    return p.n_bonds * promised_bond(p)


def promised_tranche(notional, coupon, Q, amort="bullet"):
    if amort == "level":
        principal = notional / Q
        balance = notional - principal * np.arange(Q)
        return principal + balance * coupon / 4.0
    cf = np.full(Q, notional * coupon / 4.0)
    cf[-1] += notional
    return cf


def waterfall(p: Params, C: np.ndarray):
    Q = p.maturity_q
    PA = promised_tranche(p.a_notional, p.a_coupon, Q, p.amort)
    PB = promised_tranche(p.b_notional, p.b_coupon, Q, p.amort)
    A = np.minimum(C, PA)
    B = np.minimum(C - A, PB)
    E = C - A - B
    return A, B, E, PA, PB


def stats(x):
    return {"mean": float(x.mean()), "std": float(x.std(ddof=1)),
            **{f"p{q}": float(np.percentile(x, q)) for q in (1, 5, 25, 50, 75, 95, 99)},
            "min": float(x.min()), "max": float(x.max())}


def run(p: Params, z_mm, keep_paths=False):
    tau = default_times(p, z_mm)
    CF = bond_cashflows(p, tau)
    C = CF.sum(axis=1)
    A, B, E, PA, PB = waterfall(p, C)
    n_def = (tau <= p.maturity_q / p.freq).sum(1)
    totals = {"collateral": C.sum(1), "A": A.sum(1), "B": B.sum(1), "equity": E.sum(1)}

    out = {
        "cum_pd_5y_theory": 1 - (1 - p.pd_annual) ** 5,
        "share_defaulting_5y": float((tau <= 5).mean()),
        "E_defaults": float(n_def.mean()),
        "total_cash": {k: stats(v) for k, v in totals.items()},
        "promised_total": {"collateral": float(promised_collateral(p).sum()),
                           "A": float(PA.sum()), "B": float(PB.sum())},
    }
    for cls, X, P in (("A", A, PA), ("B", B, PB)):
        short = (P - X).sum(1)
        out[cls] = {
            "P_shortfall": float((short > 1e-9).mean()),
            "P_interest_miss": float(((P[:-1] - X[:, :-1]) > 1e-9).any(1).mean()),
            "P_final_payment_shortfall": float(((P[-1] - X[:, -1]) > 1e-9).mean()),
            "expected_shortfall": float(short.mean()),
        }
    if keep_paths:
        out["_paths"] = dict(tau=tau, CF=CF, C=C, A=A, B=B, E=E, n_def=n_def, totals=totals)
    return out


def checks(p: Params, z_mm, paths):
    assert np.allclose(z_mm.mean(0), 0, atol=1e-12)
    assert np.allclose(np.cov(z_mm, rowvar=False, bias=True), np.eye(p.n_bonds), atol=1e-10)
    assert np.allclose(paths["A"] + paths["B"] + paths["E"], paths["C"])
    assert (paths["E"] >= -1e-12).all()
    zero_pd = bond_cashflows(replace(p, pd_annual=0.0), default_times(replace(p, pd_annual=0.0), z_mm))
    assert np.allclose(zero_pd.sum(1).sum(1), promised_collateral(p).sum())
    slide = Params(n_bonds=1, face=1000.0, coupon=0.055, lgd=0.60, maturity_q=5, freq=1)
    assert np.allclose(bond_cashflows(slide, np.array([[1.5]]))[0, 0], [55, 22, 22, 22, 422])
    assert np.allclose(bond_cashflows(slide, np.array([[99.0]]))[0, 0], [55, 55, 55, 55, 1055])


def show_case(p: Params, paths, case: int):
    i = case - 1
    print(f"\nCase {case}: default dates (years) by bond:", np.round(paths["tau"][i], 2))
    print(f"{'Q':>3} " + " ".join(f"{'B' + str(j + 1):>6}" for j in range(p.n_bonds))
          + f" {'TCF':>8} {'A':>7} {'B':>7} {'Equity':>8}")
    for q in range(p.maturity_q):
        print(f"{q + 1:>3} " + " ".join(f"{v:6.2f}" for v in paths["CF"][i, :, q])
              + f" {paths['C'][i, q]:8.2f} {paths['A'][i, q]:7.2f} {paths['B'][i, q]:7.2f} {paths['E'][i, q]:8.2f}")
    print(f"Totals: TCF {paths['C'][i].sum():.2f}, A {paths['A'][i].sum():.2f}, "
          f"B {paths['B'][i].sum():.2f}, equity {paths['E'][i].sum():.2f}  ($MM)")


BLUE, ORANGE, GREEN, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#52514e"


def make_charts(p: Params, P, sens, case: int, outdir: str):
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

    C, A, B, E = P["C"], P["A"], P["B"], P["E"]
    tot = P["totals"]
    Q = p.maturity_q
    PA = promised_tranche(p.a_notional, p.a_coupon, Q)
    PB = promised_tranche(p.b_notional, p.b_coupon, Q)

    nd = np.bincount(P["n_def"], minlength=p.n_bonds + 1) / p.n_cases * 100
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.bar(range(p.n_bonds + 1), nd, color=BLUE, width=.7)
    for x, y in enumerate(nd):
        if y > 0: ax.text(x, y + .5, f"{y:.1f}%", ha="center", fontsize=8, color=GREY)
    ax.set(title="How many of the 10 bonds default within 5 years?", xlabel="number of defaults",
           ylabel="% of 1,000 cases", xticks=range(p.n_bonds + 1))
    ax.grid(axis="x", visible=False)
    save(fig, "01_default_count.png")

    t = np.linspace(0, 5, 101)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(t, [(P["tau"] <= x).mean() * 100 for x in t], color=BLUE, lw=2, label="simulated (10,000 bonds)")
    ax.plot(t, (1 - (1 - p.pd_annual) ** t) * 100, color=ORANGE, lw=1.5, ls="--", label="theory 1-(1-PD)^t")
    ax.set(title="Share of bonds defaulted by each date", xlabel="years", ylabel="%")
    ax.legend()
    save(fig, "02_default_timing.png")

    q = np.arange(1, Q)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(q, C.mean(0)[:-1], color=BLUE, lw=2, label="average")
    ax.fill_between(q, np.percentile(C, 5, 0)[:-1], np.percentile(C, 95, 0)[:-1], color=BLUE, alpha=.15,
                    label="5th-95th percentile")
    ax.plot(q, promised_collateral(p)[:-1], color=GREY, ls=":", label="promised")
    ax.set(title=f"Quarterly TCF, quarters 1-19 (quarter 20 average: ${C[:, -1].mean():.1f}M incl. principal)",
           xlabel="quarter", ylabel="$M", ylim=(0, 1.7), xticks=range(1, Q, 2))
    ax.legend(loc="lower left")
    save(fig, "03_tcf_by_quarter.png")

    fig, axs = plt.subplots(2, 2, figsize=(10, 6))
    for ax, (k, name, col) in zip(axs.ravel(), [("collateral", "Collateral (10 bonds)", BLUE),
                                                ("A", "Class A", BLUE), ("B", "Class B", ORANGE),
                                                ("equity", "Equity (bank)", GREEN)]):
        x = tot[k]
        if np.ptp(x) < 1e-9:
            ax.bar([x[0]], [100], width=1.5, color=col)
            ax.set_xlim(x[0] - 5, x[0] + 5)
            ax.set_ylim(0, 135)
            ax.text(x[0], 104, f"${x[0]:.1f}M in all {len(x):,} cases (paid in full)", ha="center", fontsize=9)
        else:
            ax.hist(x, bins=np.arange(np.floor(x.min() / 4) * 4, x.max() + 8, 4), color=col, edgecolor="white",
                    weights=np.full(len(x), 100 / len(x)))
            for v, lab in [(np.percentile(x, 5), "5th pct"), (np.median(x), "median")]:
                ax.axvline(v, color=GREY, ls="--", lw=1)
                ax.text(v, ax.get_ylim()[1] * .9, f" {lab}\n ${v:.1f}M", fontsize=8, color=GREY)
        ax.set(title=f"{name}: total cash over 5 years", xlabel="$M", ylabel="% of cases")
    save(fig, "04_cash_distributions.png")

    fig, ax = plt.subplots(figsize=(8, 3.6))
    kw = dict(width=.75, edgecolor="white", linewidth=.8)
    ax.bar(q, A.mean(0)[:-1], color=BLUE, label="Class A", **kw)
    ax.bar(q, B.mean(0)[:-1], bottom=A.mean(0)[:-1], color=ORANGE, label="Class B", **kw)
    ax.bar(q, E.mean(0)[:-1], bottom=(A + B).mean(0)[:-1], color=GREEN, label="Equity", **kw)
    ax.set(title=f"Average cash per quarter by class, Q1-19 (Q20: A ${A[:, -1].mean():.1f}M, "
                 f"B ${B[:, -1].mean():.1f}M, equity ${E[:, -1].mean():.1f}M)",
           xlabel="quarter", ylabel="$M", xticks=range(1, Q, 2))
    ax.title.set_fontsize(9.5)
    ax.set_ylim(0, 1.85)
    ax.legend(ncol=3, loc="upper right")
    ax.grid(axis="x", visible=False)
    save(fig, "05_waterfall_average.png")

    c = p.face * p.coupon / 4
    floor_q, floor_T = p.n_bonds * c * (1 - p.lgd), p.n_bonds * (c + p.face) * (1 - p.lgd)
    fig, axs = plt.subplots(1, 2, figsize=(8, 3.4))
    for ax, (title, fl, ow) in zip(axs, [("Each quarter, years 1-5", floor_q, PA[0] + PB[0]),
                                         ("Final quarter (year 5)", floor_T, PA[-1] + PB[-1])]):
        ax.bar([0, 1], [fl, ow], color=[BLUE, ORANGE], width=.6)
        for x, v in zip([0, 1], [fl, ow]): ax.text(x, v * 1.02, f"${v:.1f}M", ha="center")
        ax.set_xticks([0, 1], ["pool cash if ALL\n10 bonds default", "owed to\nA + B"])
        ax.set(title=title, ylim=(0, max(fl, ow) * 1.2))
        ax.grid(axis="x", visible=False)
    axs[0].set_ylabel("$M")
    fig.suptitle("Why Class A and B are always paid in full (BIS rule)", x=.01, ha="left", fontweight="bold")
    save(fig, "06_why_A_B_safe.png")

    i = case - 1
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [1.3, 1]})
    im = axs[0].imshow(P["CF"][i][:, :-1], aspect="auto", cmap="Blues", vmin=0, vmax=c)
    axs[0].set(title=f"Case {case}: each bond's payment per quarter (Q1-19, $M)", xlabel="quarter",
               yticks=range(p.n_bonds), yticklabels=[f"Bond {j + 1} (tau {P['tau'][i, j]:.1f}y)" for j in range(p.n_bonds)],
               xticks=range(0, Q - 1, 2), xticklabels=range(1, Q, 2))
    axs[0].grid(False)
    fig.colorbar(im, ax=axs[0], fraction=.04)
    axs[1].bar(q, A[i, :-1], color=BLUE, label="A", **kw)
    axs[1].bar(q, B[i, :-1], bottom=A[i, :-1], color=ORANGE, label="B", **kw)
    axs[1].bar(q, E[i, :-1], bottom=A[i, :-1] + B[i, :-1], color=GREEN, label="Equity", **kw)
    axs[1].set(title=f"Case {case}: waterfall (TCF total ${C[i].sum():.2f}M)", xlabel="quarter", ylabel="$M",
               xticks=range(1, Q, 2))
    axs[1].legend(ncol=3, fontsize=8)
    axs[1].grid(axis="x", visible=False)
    save(fig, f"07_case_{case}.png")

    fig, axs = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    for ax, (k, title) in zip(axs, [("pd_annual", "Annual default probability"), ("lgd", "Loss given default"),
                                    ("rho", "Correlation")]):
        rows = sens[k]
        v = [r[k] for r in rows]
        ax.plot(v, [r["equity_mean"] for r in rows], "o-", color=BLUE, label="equity average")
        ax.plot(v, [r["equity_p5"] for r in rows], "o-", color=ORANGE, label="equity 5th percentile")
        ax.set(title=title, xlabel=k)
    axs[0].set_ylabel("total equity cash, $M")
    axs[0].legend(fontsize=8)
    save(fig, "08_sensitivity_equity.png")

    rows = sens["a_notional"]
    v = [r["a_notional"] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    w = 4
    ax.bar(np.array(v) - w / 2, [r["A_P_short"] * 100 for r in rows], width=w, color=BLUE, label="Class A misses")
    ax.bar(np.array(v) + w / 2, [r["B_P_short"] * 100 for r in rows], width=w, color=ORANGE, label="Class B misses")
    for x, r in zip(v, rows):
        ax.text(x + w / 2, r["B_P_short"] * 100 + 1, f"{r['B_P_short']:.1%}", ha="center", fontsize=8)
    ax.set(title="Chance of a missed payment as Class A gets bigger", xlabel="Class A notional ($M)",
           ylabel="% of cases", xticks=v)
    ax.legend()
    ax.grid(axis="x", visible=False)
    save(fig, "09_sensitivity_class_A_size.png")
    return saved


def main(case=1, outdir="results"):
    os.makedirs(outdir, exist_ok=True)
    base = Params()
    z_mm = fixed_normals(base)
    res = run(base, z_mm, keep_paths=True)
    P = res.pop("_paths")
    checks(base, z_mm, P)
    show_case(base, P, case)

    ids = np.arange(1, base.n_cases + 1)
    head = "case," + ",".join(f"bond_{j}" for j in range(1, base.n_bonds + 1))
    np.savetxt(f"{outdir}/default_times_years.csv", np.column_stack([ids, P["tau"]]),
               delimiter=",", header=head, comments="", fmt=["%d"] + ["%.6f"] * base.n_bonds)
    np.savetxt(f"{outdir}/case_totals.csv",
               np.column_stack([ids, P["n_def"], *[P["totals"][k] for k in ("collateral", "A", "B", "equity")]]),
               delimiter=",", header="case,defaults,collateral,A,B,equity", comments="",
               fmt=["%d", "%d"] + ["%.6f"] * 4)
    nd = np.bincount(P["n_def"], minlength=base.n_bonds + 1) / base.n_cases
    np.savetxt(f"{outdir}/default_count_dist.csv", np.column_stack([np.arange(base.n_bonds + 1), nd]),
               delimiter=",", header="n_defaults,probability", comments="", fmt=["%d", "%.6f"])
    qtr = np.arange(1, base.maturity_q + 1)
    cols = [qtr, promised_collateral(base), P["C"].mean(0), np.percentile(P["C"], 5, 0),
            np.percentile(P["C"], 95, 0), P["A"].mean(0), P["B"].mean(0), P["E"].mean(0)]
    np.savetxt(f"{outdir}/quarterly_expected_cf.csv", np.column_stack(cols), delimiter=",",
               header="quarter,collateral_promised,collateral_mean,collateral_p5,collateral_p95,A_mean,B_mean,equity_mean",
               comments="", fmt="%.6f")

    sens = {}
    grids = {"rho": [0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 0.95],
             "pd_annual": [0.02, 0.04, 0.06, 0.08, 0.12],
             "lgd": [0.2, 0.4, 0.6, 0.8, 1.0],
             "coupon": [0.02, 0.04, 0.06, 0.08],
             "a_notional": [20, 40, 60, 80]}
    for name, grid in grids.items():
        rows = []
        for v in grid:
            r = run(replace(base, **{name: v}), z_mm)
            rows.append({name: v, "E_defaults": r["E_defaults"],
                         "collateral_mean": r["total_cash"]["collateral"]["mean"],
                         "equity_mean": r["total_cash"]["equity"]["mean"],
                         "equity_p5": r["total_cash"]["equity"]["p5"],
                         "A_P_short": r["A"]["P_shortfall"], "B_P_short": r["B"]["P_shortfall"],
                         "A_exp_shortfall": r["A"]["expected_shortfall"],
                         "B_exp_shortfall": r["B"]["expected_shortfall"]})
        sens[name] = rows
    res["sensitivities"] = sens

    rho_cal = calibrate_rho(base, z_mm, 0.20)
    alts = [("Base case (BIS, bullet notes, normal correlation 0.20)", base),
            (f"Default dates correlated at 0.20 (normal input {rho_cal:.4f})", replace(base, rho=rho_cal)),
            ("One-time 40% par recovery instead of BIS", replace(base, recovery="par")),
            ("Notes paid down evenly each quarter", replace(base, amort="level")),
            ("4% used directly as hazard rate", replace(base, hazard="rate"))]
    alt_rows = []
    for name, ap in alts:
        r = run(ap, z_mm)
        alt_rows.append({"alternative": name, "default_date_corr": default_date_correlation(ap, z_mm),
                         "equity_mean": r["total_cash"]["equity"]["mean"],
                         "equity_p5": r["total_cash"]["equity"]["p5"],
                         "A_P_short": r["A"]["P_shortfall"], "B_P_short": r["B"]["P_shortfall"]})
    res["alternatives"] = alt_rows
    res["rho_calibrated"] = rho_cal
    with open(f"{outdir}/alternatives.csv", "w") as fh:
        fh.write(",".join(alt_rows[0]) + "\n")
        for row in alt_rows:
            fh.write(",".join(f'"{v}"' if isinstance(v, str) else f"{v:.6f}" for v in row.values()) + "\n")
    with open(f"{outdir}/sensitivities.csv", "w") as fh:
        fh.write("parameter,value,E_defaults,collateral_mean,equity_mean,equity_p5,A_P_short,B_P_short,A_exp_shortfall,B_exp_shortfall\n")
        for name, rows in sens.items():
            for row in rows:
                vals = [row[name]] + [row[k] for k in ("E_defaults", "collateral_mean", "equity_mean", "equity_p5",
                                                       "A_P_short", "B_P_short", "A_exp_shortfall", "B_exp_shortfall")]
                fh.write(name + "," + ",".join(f"{v:.6f}" for v in vals) + "\n")
    try:
        res["charts"] = make_charts(base, P, sens, case, outdir)
    except ImportError:
        res["charts"] = "matplotlib not installed: pip install matplotlib"
    res["selected_case"] = case
    res["valuation"] = "Part 2 (not yet covered in class)"

    with open(f"{outdir}/results.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="CDO cash-flow simulation (Part 1)")
    ap.add_argument("--case", type=int, default=1, help="case number to display, 1-1000")
    args = ap.parse_args()
    if not 1 <= args.case <= Params().n_cases:
        ap.error("--case must be between 1 and 1000")
    r = main(args.case)
    print("\nAll checks passed.")
    print(json.dumps({k: v for k, v in r.items() if k not in ("sensitivities", "charts", "alternatives")}, indent=2))
    print("\n== alternatives (Table 4)")
    for row in r["alternatives"]:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})
    print("\nCharts saved in results/charts/:", r["charts"])
    for name, rows in r["sensitivities"].items():
        print("\n==", name)
        for row in rows:
            print({k: round(v, 4) for k, v in row.items()})
