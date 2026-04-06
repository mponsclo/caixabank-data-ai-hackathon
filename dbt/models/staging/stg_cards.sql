with source as (
    select *
    from read_csv_auto('../data/raw/cards_data.csv', header=true)
)

select
    id as card_id,
    client_id,
    card_brand,
    card_type,
    card_number,
    expires,
    cvv,
    has_chip = 'YES' as has_chip,
    num_cards_issued,
    replace(replace(credit_limit, '$', ''), ',', '')::double as credit_limit,
    acct_open_date,
    year_pin_last_changed,
    card_on_dark_web = 'Yes' as card_on_dark_web,
    -- derived: parse expiry date (MM/YYYY format)
    make_date(
        split_part(expires, '/', 2)::int,
        split_part(expires, '/', 1)::int,
        1
    ) as expiry_date
from source
