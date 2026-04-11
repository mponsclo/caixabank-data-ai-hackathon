# Blog Post 1: Data Leakage Detection

## Metadata

- **Title:** "I Caught a Data Leak That Inflated My Fraud Model's Score by 50%"
- **Subtitle:** "How an ablation study revealed future data hiding in a SQL CTE -- and why every temporal model needs this check."
- **Target length:** 1,500--1,800 words (7-8 minute read)
- **Tags:** data-science, machine-learning, fraud-detection, feature-engineering, data-leakage
- **Publish:** Week 1

## Hook (first 2 sentences)

"My AUPRC jumped from 0.57 to 0.89. I celebrated for about ten minutes before the paranoia kicked in -- a 50% improvement from adding geographic features felt too good to be true."

## Outline

### 1. Setup: The fraud detection problem (150 words)
- 13M transactions, 0.15% fraud rate
- LightGBM + Focal Loss, already at AUPRC=0.57 after 6 experiments
- Adding geographic features (zip distance, out-of-home-state) for Exp 8

### 2. The suspicious jump (200 words)
- AUPRC shoots from 0.57 to 0.89
- "In my experience, jumps this large usually mean one of three things: (1) the feature is genuinely transformative, (2) there's a bug, or (3) there's leakage"
- Decision to run a full ablation study before celebrating

### 3. The ablation study (400 words)
- Method: add one feature at a time to the baseline, measure AUPRC independently
- **Diagram placeholder: Ablation waterfall chart** (Excalidraw Diagram 6)
- Table showing results -- zip features alone cause +0.30 jump, everything else is +0.01-0.03
- Code snippet: the ablation loop (10 lines from experiments.md)
  - Reference: `experiments.md:276-308`

### 4. Root cause: future data in a SQL CTE (400 words)
- The `client_home_zip` CTE computes most frequent zip from ALL transactions (past AND future)
- For a 2012 training transaction, the model sees 2019 zip patterns
- Since train/val split is temporal, zip becomes a proxy for time period
- **Diagram placeholder: Timeline showing how future zip leaks** (Excalidraw -- draw a timeline with training period, validation period, and an arrow from future data back to the CTE)
- Confirmation: inverse correlation -- fraud is MORE common at home zip (0.21% vs 0.04%)
- The model wasn't detecting geographic anomaly. It was detecting time.

### 5. The fix and honest results (200 words)
- Remove all zip-based features
- Honest AUPRC: 0.61 (still +7% from legitimate features: card_age_months, gap_zscore, oos_new_merchant)
- "0.61 doesn't look as impressive as 0.89, but it's real"

### 6. Takeaway: the ablation study checklist (200 words)
- When using temporal splits: every feature must be computable from historical data only
- Ablation studies are O(n_features) -- cheap insurance
- Red flags: suspiciously large jumps, features that "shouldn't" help this much, inverse correlations
- Link to full experiment log in the repo

### Closing
- "Full code, experiment logs, and the dbt SQL that caused the leak: [repo link]"
- Link to Post 2 (focal loss) if published

## Diagrams Needed
1. **Ablation waterfall** (Excalidraw Diagram 6 from plan) -- green bars for legitimate features, red bars for leaking features
2. **Temporal leakage timeline** -- shows how future data flows into a CTE that feeds training features

## Code Snippets to Include
- Ablation results table (from `experiments.md:280-291`)
- The leaking CTE (from `dbt/models/marts/mart_fraud_features.sql:22-34` -- the `client_home_zip` CTE)
