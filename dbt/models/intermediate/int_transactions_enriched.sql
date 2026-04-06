select
    t.transaction_id,
    t.transaction_date,
    t.client_id,
    t.card_id,
    t.amount,
    t.use_chip,
    t.merchant_id,
    t.merchant_city,
    t.merchant_state,
    t.zip,
    t.mcc,
    t.errors,
    coalesce(m.category_name, 'Unknown') as merchant_category
from {{ ref('stg_transactions') }} t
left join {{ ref('stg_mcc_codes') }} m on t.mcc = m.mcc
