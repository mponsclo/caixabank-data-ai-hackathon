WITH source AS (
    SELECT *
    FROM {{ ref('cards_data') }}
)

SELECT
    id AS card_id
    , client_id
    , card_brand
    , card_type
    , card_number
    , expires
    , cvv
    , has_chip = 'YES' AS has_chip
    , num_cards_issued
    , SAFE_CAST(credit_limit AS FLOAT64) AS credit_limit
    , acct_open_date
    , year_pin_last_changed
    , card_on_dark_web = 'Yes' AS card_on_dark_web
    -- derived: parse expiry date (MM/YYYY format)
    , DATE(
        CAST(SPLIT(expires, '/')[SAFE_OFFSET(1)] AS INT64),
        CAST(SPLIT(expires, '/')[SAFE_OFFSET(0)] AS INT64),
        1
    ) AS expiry_date
FROM source
