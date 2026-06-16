# Context Engine: data-engineering

Domain knowledge for **data engineering & pipelines**.

## Scope
- dbt (models, staging/marts, tests, macros, incremental, Data Vault)
- Airflow (DAG design, task dependencies, sensors, operators, Cosmos+dbt)
- Spark (transformations, partitioning, joins, broadcast, skew handling)
- Databricks (notebooks→jobs, Delta Lake, Unity Catalog, workflows)
- Data contracts & schema evolution
- Data quality (Great Expectations, dbt tests, freshness, null checks)
- Orchestration patterns (idempotency, backfills, retries, SLAs)

## Implementers
`implementers/` — dbt-models, airflow-dags, spark-jobs, databricks-jobs,
data-contracts, data-quality.

## Verifiers
`verifiers/` — idempotency, schema-contract conformance, test coverage,
partition correctness, freshness SLAs.

> 🚧 Seed file. (Cross-reference an internal tool's `data-pipeline-airflow` engine.)
