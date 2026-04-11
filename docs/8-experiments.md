# Experiments Log

The raw experiment journal: every model iteration, every metric, every failure. This is the unedited record of what was tried, what worked, and what didn't. For the curated story, see the [fraud detection guide](3-ml-fraud-detection.md) and [expense forecast guide](4-ml-expense-forecast.md).

## Task 3: Fraud Detection

### Data Overview
- **Train set**: 8,914,963 transactions (labels from `train_fraud_labels.json`)
- **Prediction set**: 2,890,952 transactions (IDs from `predictions_3.json`)
- **Fraud rate**: ~0.15% (13,332 fraud out of 8.9M) — highly imbalanced
- **Evaluation metric**: Balanced Accuracy Score
- **Features source**: `mart_fraud_features` dbt mart (29 columns)

---

### Experiment 1: LightGBM Baseline

**Config:**
- Model: `LGBMClassifier`
- n_estimators: 500, learning_rate: 0.05, max_depth: 7, num_leaves: 63
- min_child_samples: 100, is_unbalance: True
- Early stopping: 50 rounds on 15% validation split
- Features: amount, time (hour/dow/month/year/weekend), abs_amount, log_amount, is_expense, credit_limit, card_has_chip, card_on_dark_web, amount_to_limit_ratio, age, credit_score, total_debt, yearly_income, debt_to_income_ratio, use_chip, card_brand, card_type, mcc

**Results:**
- Validation Balanced Accuracy: **0.6266**
- Early stopped at iteration 2/500 (loss spiked due to `is_unbalance` reweighting)
- Recall (Fraud): 0.35, Precision (Fraud): 0.01
- Predicted fraud: 287,291 / 2,890,952 (~10%) — way too many
- Top features: txn_hour (24), txn_year (19), mcc (19), amount (15), abs_amount (15)

**Diagnosis:** Model underfitted — only 2 boosting rounds. `is_unbalance=True` caused unstable loss with early stopping. Need to use `scale_pos_weight` instead, remove early stopping or increase patience, and possibly add more discriminative features.

---

### Experiment 2: Tuned LightGBM

**Changes from Exp 1:**
- Replace `is_unbalance=True` with `scale_pos_weight` = neg/pos ratio (~668)
- Remove early stopping, use fixed 300 estimators
- Lower learning_rate to 0.01 for smoother convergence
- Increase `min_child_samples` to 500 (reduce overfitting on rare class)
- Adjust decision threshold post-training

**Results:**
- Validation Balanced Accuracy: **0.9324** (threshold=0.4)
- Recall (Fraud): 0.93, Precision (Fraud): 0.02
- All 300 estimators used (no early stopping)
- Best threshold search: 0.3→0.9306, **0.4→0.9324**, 0.5→0.9312, 0.6→0.9259, 0.7→0.9158
- Predicted fraud: 196,683 / 2,890,952 (~6.8%)
- Top features: mcc (7214), txn_year (4389), txn_hour (3283), abs_amount (2965), amount (2573)

**Analysis:** Massive jump from 0.63→0.93. `scale_pos_weight` works much better than `is_unbalance`. Precision is still very low (0.02) — model flags ~7% as fraud when real rate is 0.15%. Loss kept increasing after round 50 → overfitting. Balanced accuracy looks good but is misleading without looking at precision-recall tradeoff.

---

### Research Notes (Kaggle/Literature)

Key insights from Kaggle IEEE-CIS Fraud Detection competition and academic literature:

1. **Feature engineering is THE differentiator**, not model choice. Winners built:
   - **Velocity features**: txn count in last 1h/24h/7d per card
   - **Amount deviation**: current amount vs client's rolling average/std
   - **Time since last transaction**: inter-transaction intervals per card
   - **Merchant frequency**: how often client uses this merchant/MCC
   - **Client-level aggregates**: avg spend, spend volatility, typical hour of day

2. **Validation must respect time**: use time-series split, not random split (data leakage risk)

3. **Class imbalance**: `scale_pos_weight` is fine at scale. SMOTE only for <1M rows.

4. **Threshold tuning**: finer grid (0.01-0.99) searching for best balanced accuracy

5. **Ensemble**: XGBoost + LightGBM + CatBoost stacking wins competitions

6. **Post-processing**: average predictions by customer ID (if one card has many fraud predictions, boost others)

---

### Experiment 3: Feature-Engineered LightGBM

**Changes from Exp 2:**
- Add velocity features (txn count per card in rolling windows)
- Add amount deviation from client average
- Add time-since-last-transaction per card
- Add merchant/MCC frequency features
- Use time-based train/val split (not random) to avoid leakage
- Finer threshold grid search
- Early stopping at best validation loss

**Results (with time-based split, capped scale_pos_weight=100):**
- AUPRC: **0.2078** (up from ~0 in baseline — real signal now)
- Validation Balanced Accuracy: **0.9345** (threshold=0.05)
- Fraud Recall: 0.95, Fraud Precision: 0.02
- Predicted fraud: 155,489 / 2,890,952 (5.38%)
- All 500 estimators used (loss stable, best at ~100)
- Train: 2010-2018, Val: 2018-2019 (proper temporal split)

**Threshold-precision tradeoff (key insight):**
| Threshold | BA     | Precision | Fraud Predicted |
|-----------|--------|-----------|-----------------|
| 0.05      | 0.9345 | 0.0214    | 103,978         |
| 0.50      | 0.8465 | 0.0849    | 19,582          |
| 0.80      | 0.7301 | 0.1742    | 6,268           |
| 0.95      | 0.5831 | 0.3769    | 1,040           |

Top features now include velocity/behavioral features:
mcc (4883), txn_year (2372), txn_hour (1765), **card_merchant_freq (1558)**, **seconds_since_last_txn (1189)**, **card_amount_sum_24h (1173)**, **card_mcc_freq (1097)**

**Analysis:** Feature engineering made a massive difference in AUPRC (0→0.21). The model actually learns patterns now. Balanced accuracy is similar to Exp 2 (0.93) but with a much more meaningful model. Low threshold needed because the hackathon evaluates on balanced accuracy (rewards recall). The precision is low but that's inherent to the metric choice.

---

### Experiment 4: EDA-Informed Features + Calibrated SPW + Dual Thresholds

**Key changes:**
- Added **error features** from raw CSV: `has_bad_cvv`, `has_bad_expiration`, `has_bad_card_number`, `has_bad_pin`, `has_insufficient_balance`, `has_technical_glitch`, `has_any_error`, `card_errors_7d`
- Added **geographic anomaly**: `is_out_of_home_state` (client's most frequent state vs merchant state)
- Added **channel**: `is_online` (explicit binary)
- Added **combined risk signals**: `online_new_merchant`, `online_high_amount`
- Added **multi-card signal**: `client_distinct_cards_24h`
- Dropped `card_on_dark_web` (100% False in data)
- **Calibrated SPW=10** (systematic sweep showed SPW=10 gives best AUPRC and F1)
- 47 features total

**SPW Sweep Results (with new features):**
| SPW | AUPRC  | Best BA | Best F1 | F1 Prec | F1 Rec |
|-----|--------|---------|---------|---------|--------|
| 10  | 0.3847 | 0.9656  | 0.4108  | 0.412   | 0.409  |
| 25  | 0.3564 | 0.9649  | 0.3928  | 0.347   | 0.453  |
| 50  | 0.3530 | 0.9664  | 0.3870  | 0.392   | 0.382  |
| 100 | 0.3110 | 0.9610  | 0.3535  | 0.350   | 0.357  |
| 200 | 0.2691 | 0.9530  | 0.3322  | 0.347   | 0.319  |

**Final Model Results (SPW=10, 500 estimators):**
- **AUPRC: 0.4346** (2x improvement from Exp 3)
- **Hackathon BA: 0.9687** @ threshold=0.02 (Recall=0.98, Precision=0.04)
- **Production F1: 0.4493** @ threshold=0.56 (Precision=0.4451, Recall=0.4535)
- Train: 2010-2018, Val: 2018-2019 (proper temporal split, no leakage)

**Top 15 features:**
1. mcc (3856) — transaction category
2. txn_year (2383) — temporal pattern
3. txn_hour (1386) — time of day
4. abs_amount (1206) — transaction size
5. card_mcc_freq (1105) — behavioral frequency
6. card_amount_sum_24h (1080) — velocity
7. card_merchant_freq (951) — behavioral
8. yearly_income (945) — demographic
9. card_distinct_mcc_7d (932) — diversity
10. seconds_since_last_txn (897) — velocity
11. amount (825) — raw amount
12. **is_out_of_home_state (731)** — NEW geographic feature
13. card_txn_count_7d (711) — velocity
14. amount_to_limit_ratio (696) — utilization
15. txn_month (609)

**Key insight:** Lower `scale_pos_weight` produces a better-calibrated model. At SPW=10, the model learns genuine patterns rather than over-amplifying the minority class. The AUPRC doubled from Exp 2→4 (0.22→0.43).

---

### Experiment 5: Target Encoding + Feature Refinement

**Key changes from Exp 4:**
- **Out-of-fold target encoding** for `mcc` → `mcc_te` and `merchant_id` → `merchant_id_te`
  - 5-fold KFold (no shuffle, preserves time order)
  - Smoothing: `(fraud_count + 10 * global_mean) / (total + 10)`
- Added `client_avg_amount_last50` and `client_std_amount_last50` (were in mart but unused)
- Dropped raw `mcc` from FEATURE_COLS (replaced by `mcc_te`)
- 49 features total

**Results:**
- **AUPRC: 0.4906** (up from 0.4346 — +13% relative)
- **Hackathon BA: 0.9625** @ threshold=0.02 (Recall=0.97)
- **Production F1: 0.5144** @ threshold=0.56 (**Precision=0.5349, Recall=0.4955**)
- Predicted fraud: 90,165 / 2,890,952 (3.12%)

**Top 5 features:** `mcc_te` (2818), `txn_year` (1945), `merchant_id_te` (1627), `txn_hour` (1325), `card_amount_sum_24h` (1131)

**Analysis:** Target encoding was the single biggest win so far:
- AUPRC: 0.43 → 0.49 (+14%)
- F1: 0.45 → 0.51 (+14%)
- Precision jumped from 0.45 → **0.53** — first time above 50%
- `mcc_te` is now the #1 feature, and `merchant_id_te` is #3
- `client_std_amount_last50` entered top 20 (643) — behavioral volatility matters

For the first time we have a production-usable operating point: **53% precision at 50% recall**. Meaning half of flagged transactions are real fraud, and we catch half of all fraud.

---

### Experiment 6: Focal Loss + Hyperparameter Tuning

**Key changes from Exp 5:**
- Replaced `scale_pos_weight=10` with **focal loss** (gamma=2.0, alpha=0.25)
  - Custom objective: down-weights easy negatives, focuses on hard examples
  - Eliminates need for class weight tuning
- Increased `n_estimators` to 1000 with early stopping (patience=100)
- Increased `learning_rate` to 0.05 (focal loss has smaller gradients)
- Reduced regularization: `reg_alpha=0.5, reg_lambda=2.0`
- Reduced `min_child_samples` to 300

**Results:**
- **AUPRC: 0.5842** (up from 0.4906 — +19% relative, +35% from Exp 4)
- **Hackathon BA: 0.9683** @ threshold=0.09 (Recall=0.98)
- **Production F1: 0.5764** @ threshold=0.36 (**Precision=0.5812, Recall=0.5716**)
- Early stopped at iteration 269/1000
- Predicted fraud: 73,696 / 2,890,952 (2.55%)

**Top 5 features:** `mcc_te` (1222), `merchant_id_te` (1004), `txn_year` (766), `card_mcc_freq` (550), `txn_hour` (444)

**Analysis:** Focal loss was the biggest single-experiment improvement:
- AUPRC: 0.49 → 0.58 (+19%) — substantial
- F1: 0.51 → 0.58 (+13%)
- Precision: 0.53 → **0.58** and Recall: 0.50 → **0.57** — both improved simultaneously
- Feature importance is more evenly distributed (healthier model)
- More user/demographic features entered top 20 (credit_score, current_age, debt_to_income_ratio)

**Production operating point: 58% precision at 57% recall.** For every 10 alerts, ~6 are real fraud. And we catch 57% of all fraud. This is a genuinely usable system.

---

### Experiment 7: Ensemble Stacking (Failed)

**Attempted:** LightGBM + XGBoost + Logistic Regression meta-learner with 3-way temporal split (70/15/15).

**Results:** Catastrophic failure — AUPRC dropped from 0.58 to 0.02.

**Root cause:** The 3-way temporal split created a stacking set (15%) that landed in a low-fraud period (0.06% vs 0.15% base rate). This caused:
1. Base models trained on 30% less data
2. Meta-learner trained on a distribution shift (low-fraud period)
3. Both base models degraded individually

**Lesson:** Ensemble stacking with temporal data requires careful period selection. A 3-way split where each period has different fraud rates breaks the stacking assumption that train/stack/val come from the same distribution. Would need either: (a) larger dataset, (b) stratified temporal sampling, or (c) k-fold stacking within the training period.

**Decision:** Reverted to Exp 6 architecture (single LightGBM + focal loss) as the final model.

---

### Final Model (Exp 6 rerun, submitted)

**Architecture:** Single LightGBM with focal loss + target encoding
- **AUPRC: 0.5744**
- **Hackathon BA: 0.9672** @ threshold=0.08
- **Production F1: 0.5747** @ threshold=0.37 (**P=0.6008, R=0.5508**)
- 302 estimators (early stopped from 1000)
- 49 features

---

### Full Journey Summary

| Experiment | AUPRC | BA | F1 | Precision | Recall | Key Change |
|------------|-------|------|------|-----------|--------|------------|
| Exp 1 | ~0 | 0.63 | — | 0.01 | 0.35 | Naive baseline |
| Exp 2 | 0.22 | 0.93 | — | 0.02 | 0.93 | scale_pos_weight |
| Exp 3 | 0.21 | 0.93 | — | 0.02 | 0.95 | Velocity features |
| Exp 4 | 0.43 | 0.97 | 0.45 | 0.45 | 0.45 | EDA features + SPW=10 |
| Exp 5 | 0.49 | 0.96 | 0.51 | 0.53 | 0.50 | Target encoding |
| **Exp 6** | **0.58** | **0.97** | **0.58** | **0.60** | **0.55** | **Focal loss** |
| Exp 7 | 0.02 | 0.83 | 0.03 | — | — | Ensemble (failed) |
| Exp 8 (initial) | 0.89 | 0.99 | 0.81 | 0.83 | 0.80 | + zip features (**LEAKAGE — invalidated**) |
| **Exp 8 (fixed)** | **0.61** | **0.97** | **0.60** | **0.64** | **0.57** | **card age, amount quantile, gap zscore, interactions** |

---

### Experiment 8: Deep Feature Engineering (initial + leakage fix)

**New features added to dbt mart:**
1. **`card_age_months`** — months since account opened at transaction time. **#5 in importance (549).**
2. **`amount_vs_client_max`** — current amount / client's historical max. "How extreme is this spend?"
3. **`above_client_p90`** — binary: is amount above client's ~90th percentile.
4. **`gap_zscore`** — z-score of inter-purchase time gap vs card's rolling avg/std. **#13 (398).**
5. **`oos_new_merchant`** — compound: out-of-home-state AND new merchant.
6. **`error_online`** — compound: any error AND online transaction.
7. ~~`is_different_zip`~~ — **REMOVED: data leakage** (see below)
8. ~~`zip_region_distance`~~ — **REMOVED: data leakage** (see below)

**Leakage Discovery & Ablation:**

Initial Exp 8 showed AUPRC=0.89 — a suspiciously large jump. We ran a full ablation (adding one feature at a time):

| Feature added | AUPRC | Delta |
|---|---|---|
| Baseline (Exp 6) | 0.5724 | — |
| **+is_different_zip** | **0.8726** | **+0.30 LEAKAGE** |
| **+zip_region_distance** | **0.8761** | **+0.30 LEAKAGE** |
| +oos_new_merchant | 0.6028 | +0.030 (legitimate) |
| +amount_vs_client_max | 0.5885 | +0.016 |
| +above_client_p90 | 0.5850 | +0.013 |
| +gap_zscore | 0.5821 | +0.010 |
| +card_age_months | 0.5815 | +0.009 |
| +error_online | 0.5758 | +0.003 |

**Root cause:** `client_home_zip` CTE computes each client's most frequent zip from ALL transactions (past AND future). For a 2012 transaction, we use 2019 zip data → future leakage. Since train/val split is temporal, the model uses zip features as a proxy for "which time period is this from?", not genuine fraud signal. Also confirmed: `is_different_zip` has **inverse** correlation with fraud (fraud is MORE common at home zip: 0.21% vs 0.04%).

**Fixed Results (zip features removed, 55 features):**
- **AUPRC: 0.6149** (honest improvement from 0.5744)
- **Hackathon BA: 0.9686** @ threshold=0.08 (Recall=0.98)
- **Production F1: 0.6018** @ threshold=0.37 (**Precision=0.6353, Recall=0.5716**)
- 324 estimators (early stopped), 55 features

**Top 5 features:** `mcc_te` (1478), `merchant_id_te` (1032), `txn_year` (865), `card_mcc_freq` (585), `card_age_months` (549)

**Analysis:** Honest +7% AUPRC improvement from Exp 6 (0.57→0.61). The legitimate new features that helped:
- `card_age_months` (#5) — genuine signal, newer cards have slightly different fraud patterns
- `gap_zscore` (#13) — unusual purchase timing is a real fraud indicator
- `oos_new_merchant` — best single legitimate feature (+0.03 AUPRC)
- Production precision jumped from 0.60→**0.64** — meaningful for a bank

---

### Experiment 9: Behavioral Purchase Patterns (no improvement)

**New features attempted:**
1. `spend_acceleration` — ratio of 24h spend vs prior 24h (escalation detection)
2. `channel_switched` — did use_chip change from previous txn on same card
3. `card_testing_pattern` — prev txn <$5 and current >$100
4. `card_distinct_merchants_1h` — distinct merchants in last hour (burst diversity)
5. `min_gap_24h` — smallest inter-txn gap in 24h (burst detection)
6. `daily_utilization` — cumulative 24h spend as % of credit limit
7. `hour_deviation` — abs difference from client's typical txn hour
8. `is_night_txn` — transaction between 1-5am
9. `prev_txn_amount` — previous transaction amount on same card

**Results:**
- **AUPRC: 0.6045** (slightly WORSE than Exp 8's 0.6149)
- **F1: 0.5896** (vs 0.6018 in Exp 8)
- **P=0.6435, R=0.5440** (precision held, recall dropped)
- 64 features, 337 estimators

**Analysis:** The behavioral features added noise without signal. Only `prev_txn_amount` entered top 20 (#17 at 352 importance). The others are either too sparse (card_testing_pattern affects <1% of txns), redundant with existing velocity features, or don't correlate with fraud in this dataset. LightGBM already captures non-linear interactions between existing features — adding explicit interaction features didn't help.

**Decision:** Reverted to **Exp 8 (fixed) as the final model** (AUPRC=0.6149, F1=0.6018, P=0.64, R=0.57, 55 features).

---

### Final Model Summary

**Architecture:** LightGBM + Focal Loss (gamma=2.0, alpha=0.25) + Out-of-fold Target Encoding

| Metric | Value | Operating Point |
|--------|-------|-----------------|
| **AUPRC** | **0.6149** | — |
| **Balanced Accuracy** | **0.9686** | threshold=0.08 (hackathon submission) |
| **F1 Score** | **0.6018** | threshold=0.37 (production) |
| **Precision** | **0.6353** | 6 of 10 alerts are real fraud |
| **Recall** | **0.5716** | catch 57% of all fraud |

**Full Journey:**

| Exp | AUPRC | BA | F1 | P | R | Key Change |
|-----|-------|------|------|------|------|------------|
| 1 | ~0 | 0.63 | — | 0.01 | 0.35 | Naive baseline |
| 2 | 0.22 | 0.93 | — | 0.02 | 0.93 | scale_pos_weight |
| 3 | 0.21 | 0.93 | — | 0.02 | 0.95 | Velocity features |
| 4 | 0.43 | 0.97 | 0.45 | 0.45 | 0.45 | EDA features + SPW=10 |
| 5 | 0.49 | 0.96 | 0.51 | 0.53 | 0.50 | Target encoding |
| 6 | 0.57 | 0.97 | 0.58 | 0.60 | 0.55 | Focal loss |
| 7 | 0.02 | 0.83 | — | — | — | Ensemble (failed — temporal split) |
| 8i | 0.89 | 0.99 | 0.81 | 0.83 | 0.80 | Zip features (LEAKED) |
| **8f** | **0.61** | **0.97** | **0.60** | **0.64** | **0.57** | **Card age, amount quantile, gap zscore** |
| 9 | 0.60 | 0.97 | 0.59 | 0.64 | 0.54 | Behavioral patterns (no improvement) |

---

---

## Task 4: Expense Forecasting

### Data Overview
- **Clients**: 1,219 (98.7% predict Nov 2019–Jan 2020, rest have earlier cutoffs)
- **History**: ~118 months per client (2010-01 to 2019-10)
- **Target**: Monthly total expenses (sum of negative transaction amounts)
- **Evaluation**: R2 Score
- **Key insight**: Autocorrelation near zero (-0.01) — expenses are mostly determined by client-level characteristics (income, spending habits), not temporal patterns

### Baseline Analysis
- Naive lag-1 prediction R2: **0.5604** (most signal comes from spending *level*, not temporal dynamics)
- Coefficient of variation: ~0.62 per client — moderate month-to-month variability

### Experiment 1: Global LightGBM with Direct Forecasting

**Architecture:** One global LightGBM per horizon (h=1, h=2, h=3) with 28 features.

**Feature groups (28 total):**
- **Lag features** (5): t-1, t-2, t-3, t-6, t-12
- **Rolling statistics** (7): mean/std for 3m/6m/12m windows + median_6m
- **Seasonality** (3): month_of_year, quarter, same_month_last_year
- **Trend/momentum** (3): trend_3v12, momentum, cv_12m
- **Earnings context** (2): earn_expense_ratio, rolling_earn_mean_3m
- **Transaction patterns** (3): txn_count_lag1, txn_count_rolling_mean_3m, max_expense_ratio
- **Client demographics** (6): age, credit_score, yearly_income, total_debt, num_credit_cards, debt_to_income

**Validation:** Walk-forward, 6 folds, each tested at h=1/h=2/h=3.

**Results:**
| Horizon | R2 | Std |
|---------|------|------|
| h=1 | 0.9627 | ±0.0036 |
| h=2 | 0.9628 | ±0.0027 |
| h=3 | 0.9626 | ±0.0031 |
| **Overall** | **0.9627** | |

**Top 5 features:** earn_expense_ratio (1576), rolling_earn_mean_3m (1080), max_expense_ratio (1018), txn_count_rolling_mean_3m (522), month_of_year (375)

**Legitimacy Audit:**

Initial walk-forward reported R2=0.96, which was suspiciously high. Deep audit revealed:

| Metric | LightGBM | Client Mean Baseline |
|--------|----------|---------------------|
| **R2** | **0.88** | 0.76 |
| **MAE** | **$149** | $238 |
| **RMSE** | **$221** | $314 |
| **MAPE** | **46%** | 97% |

- **77.3% of total variance is between-client** — knowing WHO the client is explains most of R2
- **Per-client R2 (within-client): median 0.67, mean 0.44** — model captures some temporal signal but struggles with volatile clients
- **12.1% of clients have negative per-client R2** — model is worse than their own mean for these clients
- The model reduces remaining error (beyond client-mean) by **50.8%** — genuine improvement, not just memorizing levels
- The 0.96 from initial run was inflated by rolling features computed on full history before splitting. Honest R2 is **0.88**

**Prediction summary:** Mean $485, Median $343, range $0–$6,938.

**What the model actually learns:**
- Top features are earn_expense_ratio and rolling means — captures stable spending level
- month_of_year at #5 — genuine seasonality
- momentum and trend features contribute — some temporal signal
- Demographics (income, debt) help disambiguate clients

### Experiment 2: Proper Direct Forecasting + Deep Audit

**Changes from Exp 1:**
- **Proper direct targets**: each horizon h has its own target column (`expense at t+h`), trained separately
- Removed `same_month_last_year` and `quarter` (EDA showed zero seasonality, YoY corr = -0.002)
- Added: `zero_freq_6m` (frequency of zero-expense months), `rmin_6`, `rmax_6`, `range_6`, `trend_3v6`
- More validation folds (8 months) with MAE/RMSE alongside R2

**Walk-Forward Validation (honest):**
| Horizon | R2 | MAE ($) | RMSE ($) |
|---------|------|---------|----------|
| h=1 | 0.7612 | 238.73 | 313.58 |
| h=2 | 0.7613 | 238.18 | 311.95 |
| h=3 | 0.7629 | 239.99 | 314.36 |
| **Overall** | **0.7618** | **238.97** | |

**Approaches tested (all ~0.76 R2):**
| Approach | R2 |
|----------|------|
| LightGBM (4 hyperparameter configs) | 0.760-0.762 |
| Client 12m rolling mean baseline | 0.750 |
| EWMA blend (weighted lags) | 0.702 |
| alpha*LGB + (1-alpha)*rmean_6 blend | 0.727-0.762 (best at alpha=1) |
| Residual modeling (predict deviation from mean) | 0.760 |
| Two-stage (P(zero) * E[expense|nonzero]) | 0.761 |
| Huber loss | 0.015 (needs different alpha, skip) |

**Root cause of ceiling:**
- 77% of total variance is between-client → knowing WHO the client is = R2 ≈ 0.76
- Within-client autocorrelation ≈ 0 → no exploitable temporal patterns
- YoY seasonality ≈ 0 → no month-of-year effect
- 57% of clients are volatile (CV > 0.7) → their month-to-month variation is noise
- The remaining ~24% variance is **irreducible** — random spending decisions, life events, external factors

**Conclusion:** R2 ≈ 0.76 is the practical ceiling for this dataset with these features. The model has extracted all learnable signal. Further improvement would require external data (holidays, promotions, macroeconomic indicators) or transaction-level features that capture spending intent.

---
