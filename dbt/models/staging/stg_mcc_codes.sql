SELECT
    SAFE_CAST(mcc_code AS INT64) AS mcc
    , category_name
FROM {{ ref('mcc_codes') }}
