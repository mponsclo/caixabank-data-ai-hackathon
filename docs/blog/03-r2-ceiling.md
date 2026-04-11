# Blog Post 3: Forecasting Ceiling Analysis

## Metadata

- **Title:** "R2=0.76 Is the Ceiling: How I Proved My Forecasting Model Can't Improve"
- **Subtitle:** "Seven different approaches converged to the same number. Here's why that's a success, not a failure."
- **Target length:** 1,400--1,600 words (6-7 minute read)
- **Tags:** data-science, forecasting, time-series, machine-learning, statistics
- **Publish:** Week 3

## Hook

"I tested seven fundamentally different forecasting approaches on client expense data. LightGBM, EWMA, residual modeling, two-stage zero-inflated regression -- they all converged to R2=0.76. At first I thought something was broken. Then I realized I'd found the ceiling."

## Outline

### 1. The suspiciously high initial score (200 words)
- Walk-forward validation reported R2=0.96
- "Any R2 above 0.90 for monthly expense forecasting should make you uncomfortable"
- Audit revealed: rolling features computed on full history BEFORE splitting → leakage
- Fix: proper `shift()` for all rolling features, separate targets per horizon

### 2. The honest result and the obvious question (200 words)
- After fixing: R2=0.76
- "Okay, but can we do better?"
- Tried 7 alternative approaches -- table of results
  - Reference: `experiments.md:445-454`

### 3. Variance decomposition: the diagnostic (400 words)
- Key insight: decompose total variance into between-client and within-client
- **Diagram placeholder: Variance pie chart** (Excalidraw Diagram 8)
- 77% of variance is between-client: knowing WHO the client is = R2 ≈ 0.75
- Per-client R2: median 0.67, mean 0.44 -- the model captures some temporal signal but struggles with volatile clients
- 12% of clients have negative per-client R2 -- model is worse than their own mean
- Code snippet: the groupby variance decomposition (5 lines)

### 4. Why there's no signal left to exploit (300 words)
- Within-client autocorrelation ≈ 0: knowing last month tells you nothing about next month
- Year-over-year seasonality ≈ 0: no month-of-year effect (YoY correlation = -0.002)
- 57% of clients are volatile (CV > 0.7): their variation is noise, not pattern
- "The remaining ~24% of variance is irreducible -- random spending decisions, life events, promotions, emergencies"
- What would help: external data (holidays, macroeconomic indicators, transaction-level intent signals)

### 5. What the model actually learns (200 words)
- Top features: `earn_expense_ratio`, `rmean_6`, `rmean_12`, `yearly_income`
- "The model effectively predicts each client's spending level, adjusted slightly by recent momentum"
- This IS the correct behavior given the variance structure
- The 0.01 improvement over client-mean baseline comes from demographics and momentum -- real but small

### 6. Takeaway: convergence = ceiling (200 words)
- When fundamentally different approaches converge to the same metric, you've found the dataset's practical ceiling
- Variance decomposition is the diagnostic: compute between-group vs. within-group variance
- "Knowing when to stop is as important as knowing how to improve"
- R2=0.76 isn't a bad result -- it's a result that honestly captures the predictability of human spending behavior

### Closing
- "Sometimes the most mature thing a data scientist can say is: this is as good as it gets with this data."
- Link to repo and experiment log

## Diagrams Needed
1. **Variance decomposition pie chart + convergence table** (Excalidraw Diagram 8)
2. Optional: bar chart showing 7 approaches all clustered around R2=0.76

## Code Snippets to Include
- Walk-forward validation results table (from `experiments.md:438-443`)
- 7 approaches comparison table (from `experiments.md:445-454`)
- Root cause bullets (from `experiments.md:456-461`)
