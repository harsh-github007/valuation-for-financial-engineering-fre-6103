# Project 2 — Treasury Zero-Coupon Yield Curve

[Download the Excel workbook](MiniProject2%20ZCB%20Hr2917.xlsx)

## Assignment context

The visible mini-project instructions in **Lecture 2B — Bonds and rates**, slide 35, ask students to use Treasury bond observations to develop an automated procedure for continuously compounded discount rates at coupon and principal payment dates, express the curve as a function and graph, and present a methodology of less than one page with tabulated and graphical results. Python or Excel may be used.

This is a paraphrase of the recoverable assignment context. The supplied PDF clips portions of the right side of the slide, so this documentation does not claim to reproduce the complete prompt. No lecture file is included.

## Data and scope

- **Settlement date:** September 4, 2026.
- **Observations:** 353 U.S. Treasury notes and bonds.
- **Maturities:** September 15, 2026 through August 15, 2056.
- **Cash flows:** 5,627 coupon/principal records covering 245 distinct future payment dates.
- **Outputs:** zero rates and discount factors at payment dates, a smooth curve through 30 years, a chart, and bond-level pricing diagnostics.

The **Input Data** sheet contains the supplied maturity, coupon, bid, ask, and asked-yield observations. These observations are embedded in the project workbook, so the separate Treasury data workbook is not required. The data date follows the supplied files; no live market download is performed by this repository.

## Methodology

1. **Decode Treasury quotes.** Prices use 32nds plus eighths of a 32nd. For example, `99.312` decodes as `99 + (31 + 2/8) / 32 = 99.9765625`, rather than a literal decimal price.
2. **Build invoice prices.** Use the decoded bid/ask midpoint as clean price, then add accrued interest using semiannual Actual/Actual coupon conventions.
3. **Reconstruct payments.** Step backward in six-month intervals from each maturity, preserving month-end conventions. Each semiannual coupon equals half the annual coupon percentage per $100 face; principal is paid at maturity.
4. **Fit a smooth zero curve.** Use the six-parameter Nelson–Siegel–Svensson (NSS) model. The workbook reports that parameters were estimated outside Excel using multistart nonlinear least squares against dirty-price residuals. The fitting script is not part of the supplied artifacts.
5. **Discount and reprice.** Evaluate the curve at each payment date, discount the individual cash flows, sum them by bond, and compare model prices against observed prices.

With `t` in years and rates expressed as decimals:

```text
A(t, τ) = (1 − exp(−t / τ)) / (t / τ)
r(t) = β0 + β1 A(t, τ1)
       + β2 [A(t, τ1) − exp(−t / τ1)]
       + β3 [A(t, τ2) − exp(−t / τ2)]
d(t) = exp(−r(t) × t)
Model dirty price = Σ cash flow × d(payment time)
```

This is a simultaneous smooth-curve fit rather than a sequential bootstrap. The workbook measures payment times as elapsed days divided by 365, while accrued interest uses the coupon Actual/Actual convention.

## Saved fit diagnostics

| Metric | Saved value |
| --- | ---: |
| Price RMSE per $100 face | $0.147514 |
| Mean absolute pricing error | $0.088659 |
| Maximum absolute pricing error | $0.948389 |
| Bonds priced inside quoted bid/ask | 18.70% |

Within the fitted horizon, zero rates rise from approximately 3.7% at the short end to roughly 5.3–5.4% around 20–25 years, then ease to approximately 5.24% at 30 years. The fit is a smooth approximation: its residuals generally exceed the narrow bid/ask intervals, as the inside-spread statistic shows.

## Workbook guide

| Worksheet | Contents |
| --- | --- |
| Methodology | Data conventions, cash-flow construction, model, fitting, and outputs |
| Input Data | Treasury observations, quote decoding, accrued interest, model prices, and residuals |
| Cash Flows | Bond-level coupon/principal amounts linked to payment-date discount factors |
| ZCB Curve - Payment Dates | Rates and discount factors for the 245 distinct payment dates |
| ZCB Curve - Smooth Grid | Rates and discount factors on a 0.1-year grid through 30 years |
| Curve Chart | Yield-curve visualization |
| Fit Diagnostics | NSS parameters, error metrics, and implementation notes |

## Using the model

Read **Methodology**, review **Fit Diagnostics**, and then inspect the curve and bond residuals. Microsoft Excel supports the coupon functions used by the workbook.

The six fitted parameters are stored values; Excel formulas evaluate the curve and reprice cash flows using them. Updating market observations does **not** automatically rerun the external optimization. New observations require refitting parameters and, when maturities or settlement change, regenerating the payment schedules and date grid. The workbook is preserved as supplied, and the saved metrics have not been independently reproduced by rerunning the original optimizer.

The NSS long-run level parameter is negative in the supplied fit. Although the displayed curve is positive through 30 years, extrapolation far beyond that horizon can become negative and should not be inferred from the displayed results.
