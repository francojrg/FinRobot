# Investment Committee: RBRK (2026-11-23)

**Project Status: RBRK 6-Month Target Price and Recommendation (as of 2026-11-23)**

- **Stage:** Not complete. The intake sheet is not built, no thesis verdicts have been issued, and no share count reconciliation or valuation has been finalized. No TERMINATE.
- **Access decision (Option B, scoped):** I am not supplying `intake_draft.csv` because I do not hold its contents. I am authorizing a narrow re-sourcing pass against the FY2026 10-K and the Q1 FY27 10-Q, limited to the gap items below. No full restart. Searches are capped at two per item.
- **Thesis texts:** The thesis log is truncated, so I am supplying the working wording below. Full texts for T3, T4, and B must be confirmed against the original log before any final verdict.
  - **T1:** Subscription growth stays strong through fiscal 2027, supporting consensus revenue growth.
  - **T2:** Cash generation is durable, not only a function of upfront billing timing.
  - **T3:** The current valuation requires growth to stay near 29% for a decade; if growth fades, the valuation is at risk. (Truncated in log.)
  - **T4:** Operating leverage narrows losses as gross margin holds near 80% and operating expenses scale. (Truncated in log.)
  - **B:** Net cash and liquidity fund growth without dilution. (Truncated in log.)
- **Share count (decision):** Use 207.2M (latest quarter) for per-share figures, with the date stated as the latest quarter. The $21,585.3M market cap implies about 202.2M shares at $106.73. The 5M gap (about 2.4%) is flagged and not resolved here.
- **EV (decision):** Use the component-based figure of about $21.05B (market cap $21,585.3M + total debt $1,143.4M − cash and short-term investments $1,675.8M, all FY26 balance sheet and market data). The stated $21,527.5M is unreconciled and is not used.
- **Total debt (decision):** Report $1,143.4M as the carrying amount. Show sensitivity using $1,150M principal. The difference is likely unamortized issuance costs, to be confirmed if possible.
- **Q1 FY27 period end:** Treated as 2026-04-30 (assumed, pending 10-Q). Label it "NOTE: assumed, pending 10-Q" in the source field.
- **Data handling:** Cash, share count, and share price items that are "confirmed but unsourced" stay at `gap` until a source is attached. Items already in the hand-collected set (FCF FY24–FY26, FY26 revenue, subscription and margin figures) are carried with their 10-K source but need the source tag confirmed in the same pass.

**Order (one order, Senior Fundamental Analyst):**

[Senior Fundamental Analyst] Run one bounded re-sourcing pass for RBRK as of 2026-11-23, using only search_10k, the financial data tools, and the Q1 FY27 10-Q. Do not write code, do not produce files, and do not restart the full analysis. Cap searches at two per item. Report each item as `found` or `gap`, with the tool or document, the period, and the date.

1. **Total assets:** FY24 (2024-01-31), FY25 (2025-01-31), and Q1 FY27 (NOTE: assumed 2026-04-30, pending 10-Q). Required for ROA.
2. **FY24 balance sheet:** cash plus short-term investments and total debt at 2024-01-31.
3. **FY25 cash:** Confirm or reject the $705.1M figure (cash plus short-term investments at 2025-01-31). Give cash excluding short-term investments if found.
4. **Debt at 2026-01-31:** Credit facility balance (confirm the $327.9M June 2025 repayment) and convertible note carrying amount and principal ($1,150M). Confirm whether any undrawn facility remains.
5. **Cash flow source tags:** Confirm FY24–FY26 FCF ($(24.5)M, $21.6M, $237.8M) and FY26 operating cash flow ($282.9M) with their 10-K source. For T2, report the FY26 change in deferred revenue, if found, so billing timing can be assessed.
6. **Share count and price:** Confirm the most recent share count (207.2M, state the date) and the cover-page count. Confirm the $106.73 share price on 2026-11-23 with its source.

Deliver a single plain-text table: item, value, period, source, status (`found` / `gap`), and note. Then give a provisional verdict for T1, T2, T3, T4, and B using only the confirmed data, with any unresolved items marked as pending. Do not include consensus estimates, reverse-DCF output, or any target price. Do not write TERMINATE.
