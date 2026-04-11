WITH source AS (
    SELECT *
    FROM {{ ref('users_data') }}
)

SELECT
    id AS client_id
    , current_age
    , retirement_age
    , birth_year
    , birth_month
    , gender
    , address
    , latitude
    , longitude
    , SAFE_CAST(per_capita_income AS FLOAT64) AS per_capita_income
    , SAFE_CAST(yearly_income AS FLOAT64) AS yearly_income
    , SAFE_CAST(total_debt AS FLOAT64) AS total_debt
    , credit_score
    , num_credit_cards
FROM source
