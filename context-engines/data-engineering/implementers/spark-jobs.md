---
domain: data-engineering
description: Spark performance — partitioning, join strategies, and handling data skew.
---

# Spark Jobs

## Partitioning
- Aim for partitions ~128-256 MB each. Too many tiny partitions = scheduler overhead;
  too few = no parallelism + OOM.
- `spark.sql.shuffle.partitions` (default 200) is the #1 knob — tune to cluster cores and data size.
```python
df = df.repartition(200, "customer_id")    # hash-partition before a wide op on the key
# Reduce partitions WITHOUT a shuffle (e.g. before write):
df.coalesce(50).write.parquet(path)
```
- `repartition` = full shuffle (use to increase/rebalance). `coalesce` = merge only (use to shrink).
- Write partitioned tables by a low-cardinality column you filter on:
  `df.write.partitionBy("event_date").parquet(path)` — enables partition pruning on read.

## Joins
| Strategy | When |
|----------|------|
| Broadcast hash join | One side small (< ~10 MB, tunable via `autoBroadcastJoinThreshold`) |
| Sort-merge join | Both sides large |
| Bucketed join | Repeated joins on same key — pre-bucket tables |
```python
from pyspark.sql.functions import broadcast
big.join(broadcast(small_dim), "dim_id")   # forces broadcast, avoids shuffling the big side
```
Broadcasting a small dimension table eliminates a shuffle entirely — biggest single win.

## Data skew (the silent killer)
Symptom: one task runs for hours while others finish; a few keys hold most rows.
```python
# 1) Enable Adaptive Query Execution — auto-splits skewed partitions:
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
# 2) Salting for extreme skew on a join key:
from pyspark.sql import functions as F
n = 16
big = big.withColumn("salt", (F.rand()*n).cast("int"))
small = small.withColumn("salt", F.explode(F.array([F.lit(i) for i in range(n)])))
big.join(small, ["join_key", "salt"])
```

## Pitfalls
- `collect()` / `toPandas()` on big data -> driver OOM. Aggregate first.
- `count()`/`show()` everywhere -> each triggers a full recompute (lazy eval). Cache reused DFs.
- UDFs (esp. Python) break Catalyst optimization + are slow -> use built-in `pyspark.sql.functions`.
- `cache()` without `unpersist()` -> memory leak across stages.
- Many small output files -> downstream read storm; coalesce before write.
- Reading then filtering when you could partition-prune -> scans everything.

## Performance moves
- Filter and select early (column + predicate pushdown).
- Broadcast small dims; enable AQE.
- Cache only DataFrames reused 2+ times.
- Use Parquet/Delta (columnar, predicate pushdown) over CSV/JSON.

## Checklist
- [ ] shuffle.partitions tuned to data/cluster
- [ ] AQE + skewJoin enabled
- [ ] small dimensions broadcast
- [ ] no collect/toPandas on large data
- [ ] output not fragmented into tiny files
- [ ] built-ins used over Python UDFs
