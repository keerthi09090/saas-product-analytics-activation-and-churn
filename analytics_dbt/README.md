# Level 3: dbt + DuckDB analytics

This dbt project reads the five Level 1 Parquet files, types them in staging,
builds reusable account logic, and publishes dimensions, facts, and marts into
`analytics.duckdb`.

Run from this directory:

```bash
cd analytics_dbt
source ../.venv/bin/activate
dbt debug
dbt run
dbt test
```

Example DuckDB queries after `dbt run`:

```sql
select * from dim_account limit 5;
select * from mart_activation limit 10;
select * from mart_feature_adoption;
select * from mart_retention_cohorts order by cohort_week, weeks_since_start;
select * from mart_logo_churn order by month;
select * from mart_revenue_retention order by month;
select * from mart_retention_segments;
select * from mart_retention_behavior;
```

Staging and intermediate models are views. Dimensions, facts, and analytics
marts are tables. All models use DuckDB's `main` schema so the example queries
can be run without schema qualification.
