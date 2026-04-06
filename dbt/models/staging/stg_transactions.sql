with source as (
    select *
    from read_csv_auto('../data/raw/transactions_data.csv', header=true, timestampformat='%Y-%m-%d %H:%M:%S', quote='"')
)

select
    id as transaction_id,
    date::timestamp as transaction_date,
    client_id,
    card_id,
    replace(replace(amount, '$', ''), ',', '')::double as amount,
    use_chip,
    try_cast(merchant_id as integer) as merchant_id,
    merchant_city,
    merchant_state,
    zip,
    try_cast(mcc as integer) as mcc,
    nullif(trim(errors), '') as errors,

    -- error flag features (parsed from comma-separated errors field)
    case when errors ilike '%Bad CVV%' then 1 else 0 end as has_bad_cvv,
    case when errors ilike '%Bad Expiration%' then 1 else 0 end as has_bad_expiration,
    case when errors ilike '%Bad Card Number%' then 1 else 0 end as has_bad_card_number,
    case when errors ilike '%Bad PIN%' then 1 else 0 end as has_bad_pin,
    case when errors ilike '%Insufficient Balance%' then 1 else 0 end as has_insufficient_balance,
    case when errors ilike '%Technical Glitch%' then 1 else 0 end as has_technical_glitch,
    case when nullif(trim(errors), '') is not null then 1 else 0 end as has_any_error,

    -- online flag (strongest single signal: 28x fraud rate vs swipe)
    case when use_chip = 'Online Transaction' then 1 else 0 end as is_online
from source
