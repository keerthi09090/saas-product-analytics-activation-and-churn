-- Adoption is a proportion and must stay in the inclusive [0, 1] range.

select *
from {{ ref('mart_feature_adoption') }}
where adoption_rate < 0
   or adoption_rate > 1
