select
    mcc_code::integer as mcc,
    category_name
from {{ ref('mcc_codes') }}
