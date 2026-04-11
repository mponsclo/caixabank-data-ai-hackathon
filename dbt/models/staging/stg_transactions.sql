WITH source AS (
    SELECT *
    FROM {{ source('raw', 'transactions_data') }}
)

SELECT
    id AS transaction_id
    , date AS transaction_date
    , client_id
    , card_id
    , amount
    , use_chip
    , merchant_id
    , merchant_city
    , merchant_state
    , SAFE_CAST(zip AS STRING) AS zip
    , mcc
    , NULLIF(TRIM(errors), '') AS errors

    -- error flag features (parsed from comma-separated errors field)
    , IF(LOWER(COALESCE(errors, '')) LIKE '%bad cvv%', 1, 0) AS has_bad_cvv
    , IF(LOWER(COALESCE(errors, '')) LIKE '%bad expiration%', 1, 0) AS has_bad_expiration
    , IF(LOWER(COALESCE(errors, '')) LIKE '%bad card number%', 1, 0) AS has_bad_card_number
    , IF(LOWER(COALESCE(errors, '')) LIKE '%bad pin%', 1, 0) AS has_bad_pin
    , IF(LOWER(COALESCE(errors, '')) LIKE '%insufficient balance%', 1, 0) AS has_insufficient_balance
    , IF(LOWER(COALESCE(errors, '')) LIKE '%technical glitch%', 1, 0) AS has_technical_glitch
    , IF(NULLIF(TRIM(errors), '') IS NOT NULL, 1, 0) AS has_any_error

    -- online flag (strongest single signal: 28x fraud rate vs swipe)
    , IF(use_chip = 'Online Transaction', 1, 0) AS is_online
FROM source
