# Valuation for Financial Engineering — FRE-6103

Projects exploring consumer-loan valuation, the construction of a Treasury zero-coupon yield curve, and a simulation of CDO cash flows. Each project includes its model (Excel workbook or Python script) and documentation describing the problem, assumptions, methodology, and results.

## Projects

| Project | Focus | Documentation |
| --- | --- | --- |
| 1. Two-Loan Comparison | Amortization, financed fees, early repayment, and lender portfolio valuation | [Project README](projects/01-two-loan-comparison/README.md) |
| 2. Treasury Zero-Coupon Yield Curve | Treasury quote decoding, coupon cash flows, discount factors, and Nelson–Siegel–Svensson curve fitting | [Project README](projects/02-zcb-yield-curve/README.md) |
| 3. CDO Cash Flow Simulation (Part 1) | Fixed correlated default simulations, BIS defaultable bond cash flows, tranche waterfall, distributions and sensitivities | [Project README](projects/03-cdo-simulation/README.md) |

## Skills demonstrated

- **Loan valuation:** construct amortization schedules, account for financed fees, compare cash-flow borrowing rates, and evaluate early repayment using present value.
- **Credit portfolio analysis:** model expected defaults and prepayments, discount lender receipts, and assess portfolio profitability under alternative assumptions.
- **Fixed-income modeling:** decode Treasury quotes, reconstruct coupon schedules, distinguish clean and dirty prices, and evaluate a smooth zero-rate curve and its pricing residuals.
- **Credit simulation and structured products:** generate fixed, moment-matched normal draws, correlate default dates with a Cholesky factor, apply the BIS defaultable bond model, and distribute collateral cash through a CDO waterfall.

## Getting started

Download the workbook from the relevant project folder and open it in Microsoft Excel. Start with **Sheet 4 - Executive Summary** for Project 1 and **Methodology** for Project 2, then follow the supporting calculations and charts. Project 3 is a Python script: run `pip install -r requirements.txt` and `python cdo_simulation.py --case 121` in its folder, or read the paper.

The workbooks are preserved as supplied. README results describe their saved values; the spreadsheets were inspected without changing formulas or recalculating them in Excel. The Project 2 curve-fitting script is not included.

## Repository contents

```text
projects/
  01-two-loan-comparison/
    README.md
    MINI-PROJECT THE TWO-LOAN COMPARISON_hr2917 v1.0.xlsx
  02-zcb-yield-curve/
    README.md
    MiniProject2 ZCB Hr2917.xlsx
  03-cdo-simulation/
    README.md
    cdo_simulation.py
    requirements.txt
    paper/
      cdo_paper.pdf
      cdo_paper.tex
      figures/
```

The yield-curve workbook includes its Treasury observations in **Input Data**. Lecture PDFs, class examples, and other course materials are excluded. Assignment context is summarized in the project documentation rather than reproduced as lecture files.
