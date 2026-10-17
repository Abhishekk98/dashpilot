# KPI library

Industry KPI definitions as JSON, one file per Business Context industry (`"industry"` must match the
names in `core/context.py`). `core/dax.py` turns each KPI into a DAX measure when the data has a
matching column; KPIs that cannot be resolved are skipped.

Each KPI: `name`, `kind`, `format` (`currency` | `whole` | `decimal` | `percent`), `description`, plus:

| kind | fields | DAX |
|---|---|---|
| `sum` / `average` | `columns` (regex on column names) | `SUM` / `AVERAGE` of the first numeric match (fact table first) |
| `distinct` | `columns`, optional `fallback: "count_rows"` | `DISTINCTCOUNT` of an ID column |
| `count_rows` | – | `COUNTROWS` of the fact table |
| `ratio` | `numerator`, `denominator` (KPI names) | `DIVIDE([a], [b])` |
| `difference` | `a`, `b` (KPI names) | `[a] - [b]` |
| `value_rate` | `columns`, `values` (regex on cell values) | share of rows whose text column matches the values |
| `flag_rate` | `columns` | share of rows where a true/false (or 0/1) column is true |
| `flag_sum` | `columns`, `measure` | `CALCULATE([measure], flag = true)` |
