with source as (
    select *
    from read_csv_auto('../data/raw/users_data.csv', header=true)
)

select
    id as client_id,
    current_age,
    retirement_age,
    birth_year,
    birth_month,
    gender,
    address,
    latitude,
    longitude,
    replace(replace(per_capita_income, '$', ''), ',', '')::double as per_capita_income,
    replace(replace(yearly_income, '$', ''), ',', '')::double as yearly_income,
    replace(replace(total_debt, '$', ''), ',', '')::double as total_debt,
    credit_score,
    num_credit_cards
from source
