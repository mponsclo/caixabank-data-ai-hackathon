SELECT
    t.transaction_id
    , t.transaction_date
    , t.client_id
    , t.card_id
    , t.amount
    , t.use_chip
    , t.merchant_id
    , t.merchant_city
    , t.merchant_state
    , t.zip
    , t.mcc
    , t.errors
    , COALESCE(m.category_name, 'Unknown') AS merchant_category
FROM {{ ref('stg_transactions') }} t
    LEFT JOIN {{ ref('stg_mcc_codes') }} m ON t.mcc = m.mcc
