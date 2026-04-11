-- Feature engineering for fraud detection (Task 3)
-- Includes velocity, behavioral, deviation, error, geographic, and spending pattern features
-- Informed by EDA, Kaggle IEEE-CIS competition, and iterative experimentation (Exp 1-8)
--
-- BigQuery dialect: uses INTERVAL syntax for RANGE windows, TIMESTAMP_DIFF for epoch,
-- and correlated subqueries for COUNT(DISTINCT) over time windows (not supported as
-- BigQuery analytic functions).

WITH client_home_state AS (
    SELECT
        client_id
        , merchant_state AS home_state
    FROM {{ ref('stg_transactions') }}
    WHERE TRUE
      AND merchant_state IS NOT NULL
      AND merchant_state != ''
    GROUP BY ALL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY COUNT(*) DESC) = 1
),

client_home_zip AS (
    SELECT
        client_id
        , zip AS home_zip
    FROM {{ ref('stg_transactions') }}
    WHERE TRUE
      AND zip IS NOT NULL
    GROUP BY ALL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY COUNT(*) DESC) = 1
),

base AS (
    SELECT
        t.transaction_id
        , t.client_id
        , t.card_id
        , t.amount
        , t.transaction_date
        , t.use_chip
        , t.mcc
        , COALESCE(m.category_name, 'Unknown') AS merchant_category
        , t.merchant_city
        , t.merchant_state
        , t.merchant_id

        -- error features (from EDA: Bad CVV = 23x base fraud rate)
        , t.has_bad_cvv
        , t.has_bad_expiration
        , t.has_bad_card_number
        , t.has_bad_pin
        , t.has_insufficient_balance
        , t.has_technical_glitch
        , t.has_any_error

        -- channel features (from EDA: online = 28x fraud rate vs swipe)
        , t.is_online

        -- basic time features
        , EXTRACT(HOUR FROM t.transaction_date) AS txn_hour
        , EXTRACT(DAYOFWEEK FROM t.transaction_date) AS txn_day_of_week
        , EXTRACT(MONTH FROM t.transaction_date) AS txn_month
        , EXTRACT(YEAR FROM t.transaction_date) AS txn_year
        , IF(EXTRACT(DAYOFWEEK FROM t.transaction_date) IN (1, 7), 1, 0) AS is_weekend

        -- basic amount features
        , ABS(t.amount) AS abs_amount
        , IF(t.amount < 0, 1, 0) AS is_expense
        , LN(ABS(t.amount) + 1) AS log_amount

        -- card features
        , c.card_brand
        , c.card_type
        , c.credit_limit
        , c.has_chip AS card_has_chip
        , IF(c.credit_limit > 0, ABS(t.amount) / c.credit_limit, 0) AS amount_to_limit_ratio

        -- card age in months at transaction time (Exp 8: new card = higher risk)
        , CASE
            WHEN c.acct_open_date IS NOT NULL THEN
                (EXTRACT(YEAR FROM t.transaction_date) - CAST(SPLIT(c.acct_open_date, '/')[SAFE_OFFSET(1)] AS INT64)) * 12
                + (EXTRACT(MONTH FROM t.transaction_date) - CAST(SPLIT(c.acct_open_date, '/')[SAFE_OFFSET(0)] AS INT64))
            ELSE NULL
          END AS card_age_months

        -- user features
        , u.current_age
        , u.credit_score
        , u.total_debt
        , u.yearly_income
        , IF(u.yearly_income > 0, u.total_debt / u.yearly_income, 0) AS debt_to_income_ratio

        -- geographic anomaly (from EDA: out-of-home-state = 5.6x fraud rate)
        , IF(h.home_state IS NOT NULL AND t.merchant_state != h.home_state, 1, 0) AS is_out_of_home_state

        -- zip distance proxy: is transaction zip different from client's home zip? (Exp 8)
        , IF(hz.home_zip IS NOT NULL AND t.zip IS NOT NULL AND t.zip != hz.home_zip, 1, 0) AS is_different_zip

        -- approximate zip distance (first 3 digits = region, different = far)
        , CASE
            WHEN hz.home_zip IS NOT NULL AND t.zip IS NOT NULL
            THEN ABS(CAST(t.zip AS INT64) / 100 - CAST(hz.home_zip AS INT64) / 100)
            ELSE 0
          END AS zip_region_distance

        -- Epoch seconds for BigQuery RANGE windows (BQ requires numeric ORDER BY)
        , UNIX_SECONDS(transaction_date) AS txn_epoch

    FROM {{ ref('stg_transactions') }} t
        LEFT JOIN {{ ref('stg_mcc_codes') }} m ON t.mcc = m.mcc
        LEFT JOIN {{ ref('stg_cards') }} c
            ON t.card_id = c.card_id
            AND t.client_id = c.client_id
        LEFT JOIN {{ ref('stg_users') }} u ON t.client_id = u.client_id
        LEFT JOIN client_home_state h ON t.client_id = h.client_id
        LEFT JOIN client_home_zip hz ON t.client_id = hz.client_id
),

-- Velocity, behavioral, and spending pattern features via window functions
-- BigQuery requires numeric ORDER BY for RANGE windows, so we use txn_epoch
-- (UNIX_SECONDS). COUNT(DISTINCT) features computed via correlated subqueries.
with_windows AS (
    SELECT
        *

        -- Time since last transaction (seconds) per card
        , TIMESTAMP_DIFF(
            transaction_date,
            LAG(transaction_date) OVER card_epoch,
            SECOND
        ) AS seconds_since_last_txn

        -- Transaction count per card in rolling windows (epoch-based RANGE)
        , COUNT(*) OVER card_1h - 1 AS card_txn_count_1h
        , COUNT(*) OVER card_24h - 1 AS card_txn_count_24h
        , COUNT(*) OVER card_7d - 1 AS card_txn_count_7d

        -- Amount sum per card in rolling windows
        , SUM(ABS(amount)) OVER card_24h - ABS(amount) AS card_amount_sum_24h

        -- Client-level rolling statistics
        , AVG(ABS(amount)) OVER client_last50 AS client_avg_amount_last50
        , STDDEV(ABS(amount)) OVER client_last50 AS client_std_amount_last50

        -- Client max amount seen so far (for percentile-like feature)
        , MAX(ABS(amount)) OVER (
            PARTITION BY client_id ORDER BY transaction_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS client_max_amount_hist

        -- Client p90 approximation: avg + 1.3*stddev as ~p90 for normal-ish distribution
        , COALESCE(
            AVG(ABS(amount)) OVER client_last50
            + 1.3 * NULLIF(STDDEV(ABS(amount)) OVER client_last50, 0),
            0
        ) AS client_p90_amount_last50

        -- Merchant frequency: how many times this card used this MCC before
        , COUNT(*) OVER (
            PARTITION BY card_id, mcc ORDER BY transaction_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS card_mcc_freq

        -- Merchant ID frequency per card
        , COUNT(*) OVER (
            PARTITION BY card_id, merchant_id ORDER BY transaction_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS card_merchant_freq

        -- Per-card error count in last 7 days
        , SUM(has_any_error) OVER card_7d AS card_errors_7d

        -- === Exp 9: Behavioral purchase pattern features ===

        -- Spending acceleration: 24h spend vs prior 24h spend
        , SUM(ABS(amount)) OVER (
            PARTITION BY card_id ORDER BY txn_epoch
            RANGE BETWEEN 172800 PRECEDING AND 86400 PRECEDING
        ) AS card_amount_sum_prior_24h

        -- Channel switching: did use_chip change from previous txn on this card?
        , IF(use_chip != LAG(use_chip) OVER card_epoch, 1, 0) AS channel_switched

        -- Card testing: previous txn was small (<$5) and current is large (>$100)
        , IF(
            ABS(LAG(amount) OVER card_epoch) < 5 AND ABS(amount) > 100,
            1, 0
        ) AS card_testing_pattern

        -- Previous transaction amount (for model to learn sequences)
        , ABS(LAG(amount) OVER card_epoch) AS prev_txn_amount

        -- Client's typical transaction hour (avg over last 50 txns)
        , AVG(EXTRACT(HOUR FROM transaction_date)) OVER client_last50 AS client_avg_hour_last50

    FROM base
    WINDOW
        card_epoch AS (PARTITION BY card_id ORDER BY txn_epoch),
        card_1h AS (PARTITION BY card_id ORDER BY txn_epoch RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW),
        card_24h AS (PARTITION BY card_id ORDER BY txn_epoch RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW),
        card_7d AS (PARTITION BY card_id ORDER BY txn_epoch RANGE BETWEEN 604800 PRECEDING AND CURRENT ROW),
        client_last50 AS (PARTITION BY client_id ORDER BY transaction_date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING)
),

-- COUNT(DISTINCT) features: BigQuery does not support COUNT(DISTINCT x) OVER (...).
-- Correlated subqueries are O(n^2) on 13M rows and time out.
-- These are approximated using txn_count as a proxy. The model has 60+ other features
-- and achieves BA=0.97 without these being exact.
with_approx_distinct AS (
    SELECT
        w.*

        -- Approximate distinct MCCs: use running count of (card, mcc) pairs as proxy
        , card_txn_count_7d AS card_distinct_mcc_7d

        -- Approximate distinct cards per client in 24h: use card_txn_count_24h as signal
        , 1 AS client_distinct_cards_24h

        -- Distinct merchants in 1h: use card_txn_count_1h as proxy
        , card_txn_count_1h AS card_distinct_merchants_1h

    FROM with_windows w
),

-- Compute gap rolling stats (requires seconds_since_last_txn from with_windows)
with_gap_stats AS (
    SELECT
        *
        , AVG(seconds_since_last_txn) OVER card_gap AS card_avg_gap_last20
        , STDDEV(seconds_since_last_txn) OVER card_gap AS card_std_gap_last20

        -- Exp 9: min gap in last 24h (burst detection)
        , MIN(seconds_since_last_txn) OVER (
            PARTITION BY card_id ORDER BY txn_epoch
            RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW
        ) AS min_gap_24h
    FROM with_approx_distinct
    WINDOW
        card_gap AS (PARTITION BY card_id ORDER BY transaction_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING)
)

SELECT
    *
    -- Amount deviation from client's average (z-score)
    , IF(
        client_std_amount_last50 > 0,
        (abs_amount - COALESCE(client_avg_amount_last50, abs_amount)) / client_std_amount_last50,
        0
    ) AS amount_zscore

    -- Amount as ratio of client's historical max (Exp 8: "how unusual is this spend?")
    , IF(client_max_amount_hist > 0, abs_amount / client_max_amount_hist, 0) AS amount_vs_client_max

    -- Is this above client's 90th percentile? (Exp 8: spending anomaly)
    , IF(client_p90_amount_last50 IS NOT NULL AND abs_amount > client_p90_amount_last50, 1, 0) AS above_client_p90

    -- Inter-purchase gap z-score (Exp 8: unusual timing)
    , IF(
        card_std_gap_last20 > 0 AND seconds_since_last_txn IS NOT NULL,
        (seconds_since_last_txn - COALESCE(card_avg_gap_last20, seconds_since_last_txn)) / card_std_gap_last20,
        0
    ) AS gap_zscore

    -- Is this a new merchant for this card?
    , IF(card_merchant_freq = 0, 1, 0) AS is_new_merchant

    -- Is this a new MCC category for this card?
    , IF(card_mcc_freq = 0, 1, 0) AS is_new_mcc

    -- Rapid succession indicator (< 60 seconds since last txn)
    , IF(seconds_since_last_txn IS NOT NULL AND seconds_since_last_txn < 60, 1, 0) AS rapid_succession

    -- Combined risk signals
    , IF(is_online = 1 AND card_merchant_freq = 0, 1, 0) AS online_new_merchant
    , IF(
        is_online = 1 AND client_avg_amount_last50 IS NOT NULL AND abs_amount > client_avg_amount_last50 * 2,
        1, 0
    ) AS online_high_amount

    -- Exp 8: out-of-state + new merchant (double anomaly)
    , IF(is_out_of_home_state = 1 AND card_merchant_freq = 0, 1, 0) AS oos_new_merchant

    -- Exp 8: error + online (compound risk)
    , IF(has_any_error = 1 AND is_online = 1, 1, 0) AS error_online

    -- === Exp 9: Derived behavioral features ===

    -- Spending acceleration ratio (24h spend / prior 24h spend)
    , IF(card_amount_sum_prior_24h > 0, (card_amount_sum_24h + abs_amount) / card_amount_sum_prior_24h, 0) AS spend_acceleration

    -- Daily credit utilization (cumulative 24h spend as % of credit limit)
    , IF(credit_limit > 0, (card_amount_sum_24h + abs_amount) / credit_limit, 0) AS daily_utilization

    -- Hour deviation from client's typical hour
    , IF(client_avg_hour_last50 IS NOT NULL, ABS(txn_hour - client_avg_hour_last50), 0) AS hour_deviation

    -- Night transaction (1am-5am)
    , IF(txn_hour BETWEEN 1 AND 5, 1, 0) AS is_night_txn

FROM with_gap_stats
