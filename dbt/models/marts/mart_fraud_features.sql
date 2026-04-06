-- Feature engineering for fraud detection (Task 3)
-- Includes velocity, behavioral, deviation, error, geographic, and spending pattern features
-- Informed by EDA, Kaggle IEEE-CIS competition, and iterative experimentation (Exp 1-8)

with client_home_state as (
    select client_id, merchant_state as home_state
    from (
        select
            client_id, merchant_state,
            row_number() over (partition by client_id order by count(*) desc) as rn
        from {{ ref('stg_transactions') }}
        where merchant_state is not null and merchant_state != ''
        group by client_id, merchant_state
    )
    where rn = 1
),

-- Client home zip (most frequent zip) for distance computation
client_home_zip as (
    select client_id, zip as home_zip
    from (
        select
            client_id, zip,
            row_number() over (partition by client_id order by count(*) desc) as rn
        from {{ ref('stg_transactions') }}
        where zip is not null
        group by client_id, zip
    )
    where rn = 1
),

base as (
    select
        t.transaction_id,
        t.client_id,
        t.card_id,
        t.amount,
        t.transaction_date,
        t.use_chip,
        t.mcc,
        coalesce(m.category_name, 'Unknown') as merchant_category,
        t.merchant_city,
        t.merchant_state,
        t.merchant_id,

        -- error features (from EDA: Bad CVV = 23x base fraud rate)
        t.has_bad_cvv,
        t.has_bad_expiration,
        t.has_bad_card_number,
        t.has_bad_pin,
        t.has_insufficient_balance,
        t.has_technical_glitch,
        t.has_any_error,

        -- channel features (from EDA: online = 28x fraud rate vs swipe)
        t.is_online,

        -- basic time features
        extract(hour from t.transaction_date) as txn_hour,
        extract(dow from t.transaction_date) as txn_day_of_week,
        extract(month from t.transaction_date) as txn_month,
        extract(year from t.transaction_date) as txn_year,
        case when extract(dow from t.transaction_date) in (0, 6) then 1 else 0 end as is_weekend,

        -- basic amount features
        abs(t.amount) as abs_amount,
        case when t.amount < 0 then 1 else 0 end as is_expense,
        ln(abs(t.amount) + 1) as log_amount,

        -- card features
        c.card_brand,
        c.card_type,
        c.credit_limit,
        c.has_chip as card_has_chip,
        case when c.credit_limit > 0 then abs(t.amount) / c.credit_limit else 0 end as amount_to_limit_ratio,

        -- card age in months at transaction time (Exp 8: new card = higher risk)
        case
            when c.acct_open_date is not null then
                (extract(year from t.transaction_date) - split_part(c.acct_open_date, '/', 2)::int) * 12
                + (extract(month from t.transaction_date) - split_part(c.acct_open_date, '/', 1)::int)
            else null
        end as card_age_months,

        -- user features
        u.current_age,
        u.credit_score,
        u.total_debt,
        u.yearly_income,
        case when u.yearly_income > 0 then u.total_debt / u.yearly_income else 0 end as debt_to_income_ratio,

        -- geographic anomaly (from EDA: out-of-home-state = 5.6x fraud rate)
        case
            when h.home_state is not null and t.merchant_state != h.home_state then 1
            else 0
        end as is_out_of_home_state,

        -- zip distance proxy: is transaction zip different from client's home zip? (Exp 8)
        case
            when hz.home_zip is not null and t.zip is not null and t.zip != hz.home_zip then 1
            else 0
        end as is_different_zip,

        -- approximate zip distance (first 3 digits = region, different = far)
        case
            when hz.home_zip is not null and t.zip is not null
            then abs(t.zip::int / 100 - hz.home_zip::int / 100)
            else 0
        end as zip_region_distance

    from {{ ref('stg_transactions') }} t
    left join {{ ref('stg_mcc_codes') }} m on t.mcc = m.mcc
    left join {{ ref('stg_cards') }} c on t.card_id = c.card_id and t.client_id = c.client_id
    left join {{ ref('stg_users') }} u on t.client_id = u.client_id
    left join client_home_state h on t.client_id = h.client_id
    left join client_home_zip hz on t.client_id = hz.client_id
),

-- Velocity, behavioral, and spending pattern features via window functions
with_windows as (
    select
        *,

        -- Time since last transaction (seconds) per card
        extract(epoch from (
            transaction_date - lag(transaction_date) over (partition by card_id order by transaction_date)
        )) as seconds_since_last_txn,

        -- Transaction count per card in rolling windows
        count(*) over (
            partition by card_id
            order by transaction_date
            range between interval '1 hour' preceding and current row
        ) - 1 as card_txn_count_1h,

        count(*) over (
            partition by card_id
            order by transaction_date
            range between interval '24 hours' preceding and current row
        ) - 1 as card_txn_count_24h,

        count(*) over (
            partition by card_id
            order by transaction_date
            range between interval '7 days' preceding and current row
        ) - 1 as card_txn_count_7d,

        -- Amount sum per card in rolling windows
        sum(abs(amount)) over (
            partition by card_id
            order by transaction_date
            range between interval '24 hours' preceding and current row
        ) - abs(amount) as card_amount_sum_24h,

        -- Client-level rolling statistics
        avg(abs(amount)) over (
            partition by client_id
            order by transaction_date
            rows between 50 preceding and 1 preceding
        ) as client_avg_amount_last50,

        stddev(abs(amount)) over (
            partition by client_id
            order by transaction_date
            rows between 50 preceding and 1 preceding
        ) as client_std_amount_last50,

        -- Client max amount seen so far (for percentile-like feature)
        max(abs(amount)) over (
            partition by client_id
            order by transaction_date
            rows between unbounded preceding and 1 preceding
        ) as client_max_amount_hist,

        -- Client p90 approximation: use max of last 50 * 0.9 as proxy
        -- (DuckDB doesn't support percentile as window function)
        -- Instead: use avg + 1.3*stddev as ~p90 approximation for normal-ish distribution
        coalesce(
            avg(abs(amount)) over (
                partition by client_id order by transaction_date
                rows between 50 preceding and 1 preceding
            ) + 1.3 * nullif(stddev(abs(amount)) over (
                partition by client_id order by transaction_date
                rows between 50 preceding and 1 preceding
            ), 0),
            0
        ) as client_p90_amount_last50,

        -- (gap rolling stats computed in next CTE since they depend on seconds_since_last_txn)

        -- Merchant frequency: how many times this card used this MCC before
        count(*) over (
            partition by card_id, mcc
            order by transaction_date
            rows between unbounded preceding and 1 preceding
        ) as card_mcc_freq,

        -- Merchant ID frequency per card
        count(*) over (
            partition by card_id, merchant_id
            order by transaction_date
            rows between unbounded preceding and 1 preceding
        ) as card_merchant_freq,

        -- Distinct MCCs per card in last 7 days
        count(distinct mcc) over (
            partition by card_id
            order by transaction_date
            range between interval '7 days' preceding and current row
        ) as card_distinct_mcc_7d,

        -- Client-level: distinct cards used in last 24h (multi-card fraud signal)
        count(distinct card_id) over (
            partition by client_id
            order by transaction_date
            range between interval '24 hours' preceding and current row
        ) as client_distinct_cards_24h,

        -- Per-card error count in last 7 days
        sum(has_any_error) over (
            partition by card_id
            order by transaction_date
            range between interval '7 days' preceding and current row
        ) as card_errors_7d,

        -- === Exp 9: Behavioral purchase pattern features ===

        -- Spending acceleration: 24h spend vs prior 24h spend
        sum(abs(amount)) over (
            partition by card_id
            order by transaction_date
            range between interval '48 hours' preceding and interval '24 hours' preceding
        ) as card_amount_sum_prior_24h,

        -- Channel switching: did use_chip change from previous txn on this card?
        case when use_chip != lag(use_chip) over (partition by card_id order by transaction_date)
             then 1 else 0 end as channel_switched,

        -- Card testing: previous txn was small (<$5) and current is large (>$100)
        case when abs(lag(amount) over (partition by card_id order by transaction_date)) < 5
              and abs(amount) > 100 then 1 else 0 end as card_testing_pattern,

        -- Previous transaction amount (for model to learn sequences)
        abs(lag(amount) over (partition by card_id order by transaction_date)) as prev_txn_amount,

        -- Distinct merchants in 1h (burst diversity)
        count(distinct merchant_id) over (
            partition by card_id
            order by transaction_date
            range between interval '1 hour' preceding and current row
        ) as card_distinct_merchants_1h,

        -- Client's typical transaction hour (avg over last 50 txns)
        avg(extract(hour from transaction_date)) over (
            partition by client_id
            order by transaction_date
            rows between 50 preceding and 1 preceding
        ) as client_avg_hour_last50

    from base
),

-- Compute gap rolling stats (requires seconds_since_last_txn from with_windows)
with_gap_stats as (
    select
        *,
        avg(seconds_since_last_txn) over (
            partition by card_id
            order by transaction_date
            rows between 20 preceding and 1 preceding
        ) as card_avg_gap_last20,

        stddev(seconds_since_last_txn) over (
            partition by card_id
            order by transaction_date
            rows between 20 preceding and 1 preceding
        ) as card_std_gap_last20,

        -- Exp 9: min gap in last 24h (burst detection)
        min(seconds_since_last_txn) over (
            partition by card_id
            order by transaction_date
            range between interval '24 hours' preceding and current row
        ) as min_gap_24h
    from with_windows
)

select
    *,
    -- Amount deviation from client's average (z-score)
    case
        when client_std_amount_last50 > 0
        then (abs_amount - coalesce(client_avg_amount_last50, abs_amount)) / client_std_amount_last50
        else 0
    end as amount_zscore,

    -- Amount as ratio of client's historical max (Exp 8: "how unusual is this spend?")
    case
        when client_max_amount_hist > 0
        then abs_amount / client_max_amount_hist
        else 0
    end as amount_vs_client_max,

    -- Is this above client's 90th percentile? (Exp 8: spending anomaly)
    case
        when client_p90_amount_last50 is not null and abs_amount > client_p90_amount_last50 then 1
        else 0
    end as above_client_p90,

    -- Inter-purchase gap z-score (Exp 8: unusual timing)
    case
        when card_std_gap_last20 > 0 and seconds_since_last_txn is not null
        then (seconds_since_last_txn - coalesce(card_avg_gap_last20, seconds_since_last_txn)) / card_std_gap_last20
        else 0
    end as gap_zscore,

    -- Is this a new merchant for this card?
    case when card_merchant_freq = 0 then 1 else 0 end as is_new_merchant,

    -- Is this a new MCC category for this card?
    case when card_mcc_freq = 0 then 1 else 0 end as is_new_mcc,

    -- Rapid succession indicator (< 60 seconds since last txn)
    case when seconds_since_last_txn is not null and seconds_since_last_txn < 60 then 1 else 0 end as rapid_succession,

    -- Combined risk signals
    case when is_online = 1 and card_merchant_freq = 0 then 1 else 0 end as online_new_merchant,
    case
        when is_online = 1 and client_avg_amount_last50 is not null and abs_amount > client_avg_amount_last50 * 2 then 1
        else 0
    end as online_high_amount,

    -- Exp 8: out-of-state + new merchant (double anomaly)
    case
        when is_out_of_home_state = 1 and card_merchant_freq = 0 then 1
        else 0
    end as oos_new_merchant,

    -- Exp 8: error + online (compound risk)
    case
        when has_any_error = 1 and is_online = 1 then 1
        else 0
    end as error_online,

    -- === Exp 9: Derived behavioral features ===

    -- Spending acceleration ratio (24h spend / prior 24h spend)
    case
        when card_amount_sum_prior_24h > 0
        then (card_amount_sum_24h + abs_amount) / card_amount_sum_prior_24h
        else 0
    end as spend_acceleration,

    -- Daily credit utilization (cumulative 24h spend as % of credit limit)
    case
        when credit_limit > 0
        then (card_amount_sum_24h + abs_amount) / credit_limit
        else 0
    end as daily_utilization,

    -- Hour deviation from client's typical hour
    case
        when client_avg_hour_last50 is not null
        then abs(txn_hour - client_avg_hour_last50)
        else 0
    end as hour_deviation,

    -- Night transaction (1am-5am)
    case when txn_hour between 1 and 5 then 1 else 0 end as is_night_txn

from with_gap_stats
