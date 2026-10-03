# Project 1 — Two-Loan Comparison

[Download the Excel workbook](MINI-PROJECT%20THE%20TWO-LOAN%20COMPARISON_hr2917%20v1.0.xlsx)

## Problem and questions addressed

A borrower needs $5,000 for two years and will make monthly payments. Compare Chase's 10% annual loan with no origination fee against Wells Fargo's 7% annual loan with a 2% financed origination fee.

The following questions summarize the analysis implemented in the workbook. They are reconstructed from its contents because a complete two-loan assignment prompt could not be recovered from the supplied class PDFs.

1. What are the monthly payments, amortization schedules, total interest, and total borrower costs for each loan?
2. How does financing the origination fee affect the effective borrowing rate and the preferred loan?
3. After each monthly payment, how does the outstanding balance compare with the present value of remaining payments discounted at Chase's rate? When is early repayment economically attractive under that assumption?
4. What is a portfolio of 1,000 Wells Fargo loans worth when funding costs, defaults, and prepayments are included?
5. How do alternative assumptions affect portfolio value?

The supplied **Lecture 2A — Loans with exponential default risk** provides related context on amortization, default-adjusted cash flows, prepayment, and lender profitability. The lecture itself is not included.

## Assumptions

| Input | Chase | Wells Fargo |
| --- | ---: | ---: |
| Cash received by borrower | $5,000 | $5,000 |
| Term | 24 months | 24 months |
| Annual contract rate | 10% | 7% |
| Monthly contract rate | 10% / 12 | 7% / 12 |
| Origination fee | 0% | 2% |
| Amount financed | $5,000 | $5,100 |

The Wells Fargo fee is added to principal. The borrower receives $5,000 and repays a $5,100 financed balance. Payments occur monthly, with no rounding of the underlying payment calculation.

For early repayment, both loans' remaining payments are discounted at 10% / 12 per month. The lender portfolio assumes 1,000 loans, a 2% annual cost of funds, 0.5% monthly defaults with zero recovery, and 1% monthly prepayments. Defaulting loans make no current payment; prepaying loans make the scheduled payment and then repay the remaining balance.

## Methodology

For principal `P`, monthly rate `r`, and term `n`, the payment is:

```text
C = P × r / (1 − (1 + r)^−n)
Interest = Beginning balance × r
Principal reduction = C − Interest
Ending balance = Beginning balance − Principal reduction
```

The payoff analysis compares each ending balance with the annuity present value of the remaining payments. The borrower rate calculation uses `RATE` on the actual $5,000 cash received and the 24 payments. The reported nominal APR is monthly cash-flow IRR multiplied by 12, rather than the compounded effective annual rate.

The bank model tracks the surviving pool and aggregates scheduled interest, principal, and prepayment receipts. Discounted receipts less the $5 million initially advanced give portfolio NPV. An additional schedule rounds defaults and prepayments to whole loans, while the main schedule uses fractional expected counts. The sheet also contains sensitivity calculations.

## Saved results

| Metric | Chase | Wells Fargo |
| --- | ---: | ---: |
| Monthly payment | $230.72 | $228.34 |
| Total scheduled payments | $5,537.39 | $5,480.16 |
| Interest | $537.39 | $380.16 |
| Origination fee | $0.00 | $100.00 |
| Interest plus fee | $537.39 | $480.16 |
| Nominal APR including fee | 10.00% | 8.96% |

Wells Fargo saves $2.38 per month and $57.23 over the full scheduled term. Under the 10% discount-rate assumption, Chase's balance equals the present value of its remaining payments. Wells Fargo's balance exceeds that present value before maturity, so early repayment sacrifices value under that assumption.

The bank's saved base-case portfolio value is **$5,050,507.65**, giving an NPV of **$50,507.65** after the $5 million advance, or about **1.01% per dollar advanced**. These results depend on the workbook's payment timing and default/prepayment assumptions.

## Workbook guide

| Worksheet | Contents |
| --- | --- |
| Sheet 1 - Amortization & Charts | Inputs, payment formulas, both 24-month schedules, and charts |
| Sheet 2 - Payoff Analysis | Outstanding balances versus discounted remaining payments |
| Sheet 3 - Bank's View | Portfolio cash flows, expected and rounded loan counts, sensitivity analysis, and NPV |
| Sheet 4 - Executive Summary | Borrower comparison, fee-adjusted borrowing rates, and recommendation |

Open the executive summary first. Review the assumptions before interpreting the recommendation. Changing the loan inputs may also require updating repeated assumptions on other sheets; the supplied workbook has not been redesigned.
