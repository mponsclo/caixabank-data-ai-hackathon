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
    t.mcc,
    t.merchant_category,
    -- user features
    u.current_age,
    u.retirement_age,
    u.credit_score,
    u.total_debt,
    u.yearly_income,
    u.per_capita_income,
    u.gender,
    -- card features
    c.card_brand,
    c.card_type,
    c.credit_limit,
    c.has_chip as card_has_chip,
    c.card_on_dark_web,
    c.expiry_date as card_expiry_date
from {{ ref('int_transactions_enriched') }} t
left join {{ ref('stg_users') }} u on t.client_id = u.client_id
left join {{ ref('stg_cards') }} c on t.card_id = c.card_id and t.client_id = c.client_id
